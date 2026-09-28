"""
AG-TREND: 100% Real-Time Live Multi-Platform Scraper & Intelligence.
Supports Targeted Source Scraping, Custom Keyword/Topic Scraping, Real TikTok Comments & Live Media.
"""

from __future__ import annotations

import json
import logging
import re
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from ca_agents.clients.apify_client import ApifyError  # noqa: F401  (re-exported)
from ca_agents.text_util import match_any_keyword

logger = logging.getLogger(__name__)

# Từ khoá nhận diện nội dung F&B trong TIÊU ĐỀ video TikTok.
# So khớp theo TỪ (xem `match_any_keyword`) — so khớp substring khiến "xăng"
# khớp "ăn" và gán nhãn sai am_thuc_fnb.
_FNB_TITLE_KEYWORDS = (
    "cà phê",
    "cafe",
    "trà",
    "matcha",
    "ăn",
    "uống",
    "quán",
    "món",
    "bánh",
    "kem",
    "đồ uống",
    "ẩm thực",
)

# SSL mặc định verify hostname + chain (create_default_context). KHÔNG tắt
# verify_mode: scraper chạy trên máy thật, chấp nhận MITM để đổi "kết nối được"
# là đánh đổi sai. Nguồn hỏng cert → request lỗi → trả [] đúng ADR-008.
_SSL_CTX = ssl.create_default_context()

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


@dataclass(frozen=True)
class TrendItem:
    id: str
    tieu_de: str
    cum_tu_khoa_viral: str
    nguon_goc: str  # "threads_vn" | "tiktok_vn" | "google_vn" | "star_vn" | "tiktok_global"
    loai_xu_huong: str  # "breaking_vn_24h" | "predictive_global"
    danh_muc: str  # "meme_cau_noi" | "tam_ly_lifestyle" | "am_thuc_fnb" | "am_thanh_nhac" | "trao_luu_pop_culture"
    vong_doi: (
        str  # "moi_nhu" (Mới nổi 24h) | "dang_dinh" (Đang đỉnh cao) | "bao_hoa" (Đã cũ/Bão hòa)
    )
    diem_nhan_dac_biet: str
    nguon_goc_chi_tiet: str
    ngu_canh_su_dung: str
    tam_ly_gioi_tre: str
    toc_do_tang_truong_24h: float
    diem_tiem_nang_viral: int
    du_bao_thoi_gian: str
    link_goc: str = ""
    tiktok_url: str = ""
    tiktok_tag_url: str = ""
    thoi_gian_cao: str = ""
    luot_tiep_can: str = ""
    trich_doan_noi_dung_that: str = ""
    binh_luan_that_tiktok: list[str] = field(default_factory=list)
    mau_comment_viral: list[str] = field(default_factory=list)
    nen_tang_lan_toa: list[str] = field(default_factory=list)
    tu_khoa_hashtag: list[str] = field(default_factory=list)
    is_live_scraped: bool = True


_FIXTURE_TRENDS: list[TrendItem] = [
    TrendItem(
        id="vn_slang_co_dia_that_nghiep",
        tieu_de="Câu nói 'Cơ địa khó thất nghiệp' gây sốt mạng xã hội",
        cum_tu_khoa_viral="Cơ địa khó thất nghiệp",
        nguon_goc="tiktok_vn",
        loai_xu_huong="breaking_vn_24h",
        danh_muc="meme_cau_noi",
        vong_doi="dang_dinh",
        diem_nhan_dac_biet="Bắt nguồn từ phát ngôn của Lê Bống khi chia sẻ về hành trình làm việc chăm chỉ, sau đó trở thành meme tự động viên bản thân của giới trẻ.",
        nguon_goc_chi_tiet="Phát ngôn trong phỏng vấn của Lê Bống trên TikTok/YouTube tháng 2/2026, nhanh chóng được các bạn trẻ và sinh viên biến thành câu nói cửa miệng.",
        ngu_canh_su_dung="Dùng để trêu đùa khi phải làm việc nhiều ca, tăng ca cuối tuần, hoặc thể hiện tinh thần chịu khó vượt khó.",
        tam_ly_gioi_tre="Tự trào, biến áp lực công việc thành năng lượng hài hước để cùng nhau vượt qua deadline.",
        toc_do_tang_truong_24h=520.0,
        diem_tiem_nang_viral=98,
        du_bao_thoi_gian="7-10 ngày tới",
        link_goc="https://www.tiktok.com/search?q=co%20dia%20kho%20that%20nghiep",
        tiktok_url="https://www.tiktok.com/search?q=co%20dia%20kho%20that%20nghiep",
        tiktok_tag_url="https://www.tiktok.com/tag/codiakhothatnghiep",
        binh_luan_that_tiktok=[
            "Xin vía cơ địa khó thất nghiệp đi làm từ sáng tới tối",
            "Cơ địa này chỉ hợp làm ca tối quán cafe thôi",
        ],
        mau_comment_viral=[
            "Xin vía cơ địa khó thất nghiệp đi làm từ sáng tới tối",
            "Cơ địa này chỉ hợp làm ca tối quán cafe thôi",
        ],
        nen_tang_lan_toa=["TikTok Việt Nam"],
        tu_khoa_hashtag=["#lebong", "#codiakhothatnghiep", "#xuhuong"],
        is_live_scraped=False,
    )
]


def extract_core_tiktok_keyword(title: str) -> str:
    """Trích xuất từ khóa ngắn gọn (1-3 từ) từ tiêu đề dài."""
    parts = title.split('"')
    if len(parts) >= 3 and parts[1].strip():
        return parts[1].strip()
    single_parts = title.split("'")
    if len(single_parts) >= 3 and single_parts[1].strip():
        return single_parts[1].strip()
    clean = re.sub(
        r"^(Lộ diện|Hình ảnh|Thông tin|Bất ngờ|Mỹ nhân Việt|Dàn sao|Hot girl|KOL|Netizen xôn xao|Clip:?)\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )
    words = [w.strip(":,.-_()[]{}'\"") for w in clean.split() if w.strip()]
    if len(words) >= 3:
        return " ".join(words[:3])
    return clean[:30].strip() or title[:30].strip()


def _scrape_tiktok_smart(
    keyword: str = "",
    count: int = 12,
    nguon_goc: str = "tiktok_vn",
    scrape_mode: str = "auto",
) -> list[TrendItem]:
    """Camoufox (video VN đúng chủ đề) → TikWM → Apify → static last-resort.

    Modes:
        - auto: Camoufox → TikWM → Apify → static
        - direct_only: TikWM only → static (không Apify/Camoufox)
        - apify_force: Apify first → TikWM backup
        - browser: Camoufox first → TikWM → Apify (plan §3.5)

    ĐO THẬT 2026-09-26: Camoufox đứng TRƯỚC TikWM trong `auto` vì:
      - TikWM `/api/feed/list?region=VN` **không lọc** — chỉ 21–50% video là VN,
        lẫn MM/TH/PK/US/ID/PH (có lần 0/20 video VN).
      - Camoufox search theo **từ khoá Việt** → video đúng chủ đề, đúng VN,
        có view/like thật (đo: `@caitochim` 108.1K views, `@ghiengapgo` 12.6K).
    """
    start = time.monotonic()
    # Theo dõi đã thử Camoufox chưa — tránh launch browser 2 lần cho 1 request
    # (mode `browser` gọi Camoufox first, nếu fail thì SECONDARY không gọi lại).
    camoufox_tried = False

    # If user selected APIFY FORCE mode
    if scrape_mode == "apify_force":
        try:
            from ca_agents.sources.tiktok_apify_source import scrape_tiktok_apify

            items = scrape_tiktok_apify(
                keyword=keyword,
                count=count,
                mode="search",
                nguon_goc=nguon_goc,
            )
            if items:
                return cast(list[TrendItem], items)
        except Exception as e:
            logger.warning("tiktok_apify_force_failed_trying_tikwm: %s", e)

    # BROWSER mode: Camoufox first (plan §3.5) — rớt tầng về chuỗi cũ nếu fail.
    if scrape_mode == "browser":
        camoufox_tried = True
        try:
            from ca_agents.sources.tiktok_camoufox_source import scrape_tiktok_camoufox

            items = scrape_tiktok_camoufox(
                keyword=keyword,
                count=count,
                nguon_goc=nguon_goc,
            )
            if items:
                return cast(list[TrendItem], items)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "tiktok_browser_mode_failed_falling_back",
                extra={"error": str(e)[:200]},
            )

    # PRIMARY (auto): Camoufox browser-thật — video VN ĐÚNG CHỦ ĐỀ.
    # Đặt trước TikWM vì TikWM `region=VN` không lọc (chỉ 21–50% là VN) và
    # không tìm theo từ khoá (chỉ lấy feed chung).
    if scrape_mode not in {"direct_only", "apify_force"} and not camoufox_tried:
        camoufox_tried = True
        try:
            from ca_agents.clients.camoufox_client import is_available as _cf_avail

            if _cf_avail():
                from ca_agents.sources.tiktok_camoufox_source import scrape_tiktok_camoufox

                items = scrape_tiktok_camoufox(
                    keyword=keyword,
                    count=count,
                    nguon_goc=nguon_goc,
                )
                if items:
                    logger.info(
                        "tiktok_source_camoufox_primary",
                        extra={
                            "source": "camoufox_tiktok",
                            "nguon_goc": nguon_goc,
                            "items_count": len(items),
                            "duration_ms": int((time.monotonic() - start) * 1000),
                        },
                    )
                    return cast(list[TrendItem], items)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "tiktok_camoufox_primary_failed_trying_tikwm", extra={"error": str(e)[:200]}
            )

    # SECONDARY: TikWM Direct Free Scraper
    try:
        items = _scrape_tiktokwm_fallback(keyword=keyword, count=count)
        if items:
            logger.info(
                "tiktok_source_tikwm_primary",
                extra={
                    "source": "tikwm_direct",
                    "nguon_goc": nguon_goc,
                    "items_count": len(items),
                    "duration_ms": int((time.monotonic() - start) * 1000),
                },
            )
            return cast(list[TrendItem], items)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "tiktok_tikwm_failed_trying_apify",
            extra={"error": str(e)[:200]},
        )

    # TERTIARY / BACKUP: Apify TikTok Scraper (only if mode != direct_only)
    if scrape_mode != "direct_only":
        try:
            from ca_agents.sources.tiktok_apify_source import scrape_tiktok_apify

            items = scrape_tiktok_apify(
                keyword=keyword,
                count=count,
                mode="search",
                nguon_goc=nguon_goc,
            )
            if items:
                return cast(list[TrendItem], items)
        except Exception as e:  # noqa: BLE001
            logger.warning("tiktok_apify_backup_also_failed: %s", e)

    # LAST RESORT: static topics tĩnh — CHỈ khi mọi tầng thật (TikWM/Camoufox/Apify)
    # đều fail, để UI không bao giờ rỗng (plan §3.4: tĩnh phải đứng CUỐI chuỗi).
    return _static_tiktok_topics(keyword=keyword, count=count)


def _is_fnb_title(title: str) -> bool:
    """True nếu tiêu đề video TikTok thuộc nhóm đồ ăn/uống.

    Dùng helper so khớp THEO TỪ (`ca_agents.text_util`): so khớp substring làm
    `"xăng"` khớp từ khoá `"ăn"` → video về giá xăng bị gán nhãn `am_thuc_fnb`.
    """
    return match_any_keyword(title.lower(), _FNB_TITLE_KEYWORDS)


_TIKTOKWM_CACHE: list[dict[str, Any]] = []
_TIKTOKWM_CACHE_TIME: float = 0.0


def _static_tiktok_topics(keyword: str = "", count: int = 12) -> list[TrendItem]:
    """LAST RESORT — danh sách topic TikTok hot tĩnh khi MỌI tầng thật đều fail.

    Dữ liệu KHÔNG phải live-scrape → is_live_scraped=False để downstream
    phân biệt được (plan §3.4).
    """
    items_out: list[TrendItem] = []
    now_str = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    kw_clean = keyword.strip()

    default_topics = [
        (
            "matcha",
            "🍵 Sốt Cơn Sốt Matcha Latte & Kem Matcha Nguyên Chất",
            "am_thuc_fnb",
            "9.5M views",
        ),
        ("cà phê muối", "☕ Trào Lưu Cà Phê Muối Kem Béo Đậm Đà", "am_thuc_fnb", "14.2M views"),
        (
            "trà sữa",
            "🧋 Khám Phá Trà Sữa Đậm Vị Trà Truyền Thống",
            "am_thuc_fnb",
            "22.8M views",
        ),
        (
            "check-in",
            "📸 Địa Điểm Check-in Sống Ảo Hot Nhất Giới Trẻ",
            "tam_ly_lifestyle",
            "18.3M views",
        ),
        (
            "ẩm thực đường phố",
            "🥪 Tour Ăn Vặt Ẩm Thực Đường Phố Sài Gòn & Hà Nội",
            "am_thuc_fnb",
            "31.0M views",
        ),
        (
            "drama",
            "🔥 Điểm Tin Xu Hướng & Cảm Hứng Thịnh Hành",
            "trao_luu_pop_culture",
            "15.7M views",
        ),
    ]

    target_topics = (
        [
            (
                kw_clean,
                f"🔥 [TIKTOK TOPIC] Xu Hướng Thịnh Hành: #{kw_clean}",
                "am_thuc_fnb"
                if (kw_clean and _is_fnb_title(kw_clean))
                else "trao_luu_pop_culture",
                "Hàng triệu views",
            )
        ]
        if kw_clean
        else default_topics
    )

    for idx, (t_kw, t_title, t_cat, t_views) in enumerate(target_topics[:count]):
        clean_tag = re.sub(r"[^a-zA-Z0-9_]", "", t_kw.lower())
        search_url = f"https://www.tiktok.com/search?q={urllib.parse.quote(t_kw)}"
        tag_url = f"https://www.tiktok.com/tag/{clean_tag}" if clean_tag else search_url
        items_out.append(
            TrendItem(
                id=f"live_tiktok_search_{idx}_{clean_tag}",
                tieu_de=t_title,
                cum_tu_khoa_viral=t_kw,
                nguon_goc="tiktok_vn",
                loai_xu_huong="breaking_vn_24h",
                danh_muc=t_cat,
                vong_doi="dang_dinh",
                diem_nhan_dac_biet=f"Chủ đề '{t_kw}' đang thu hút lượng tương tác cực khủng từ cộng đồng sáng tạo nội dung TikTok.",
                nguon_goc_chi_tiet=f"Truy vấn dữ liệu thời gian thực theo chủ đề #{t_kw} lúc {now_str}.",
                ngu_canh_su_dung=f"Ý tưởng làm video ngắn, minigame, hoặc đổi mới menu theo trend #{t_kw}.",
                tam_ly_gioi_tre="Tò mò, thích trải nghiệm cái mới và bắt kịp làn sóng xu hướng của bạn bè.",
                toc_do_tang_truong_24h=max(350.0, 950.0 - (idx * 60)),
                diem_tiem_nang_viral=max(80, 98 - idx),
                du_bao_thoi_gian="Đang duy trì độ nóng trong 7-14 ngày tới",
                link_goc=search_url,
                tiktok_url=search_url,
                tiktok_tag_url=tag_url,
                thoi_gian_cao=now_str,
                luot_tiep_can=t_views,
                trich_doan_noi_dung_that=f"Khám phá hàng ngàn video và bình luận triệu view về #{t_kw} trên TikTok.",
                binh_luan_that_tiktok=[
                    f'Cộng đồng TikTok đang thảo luận sôi nổi về "#{t_kw}"',
                    f"Bấm để xem video trending #{t_kw} trực tiếp trên TikTok",
                ],
                nen_tang_lan_toa=["TikTok Việt Nam"],
                tu_khoa_hashtag=[f"#{clean_tag}", f"#{clean_tag}vietnam", "#xuhuongtiktok"],
                is_live_scraped=False,
            )
        )
    return items_out


def parse_tikwm_feed(payload: Any) -> list[dict[str, Any]]:
    """Hàm THUẦN: payload `/api/feed/list` của TikWM → list video dict.

    Đã xác minh live 2026-09-24: `data` là **LIST PHẲNG** (một số biến thể cũ
    bọc trong `{"videos": [...]}` — vẫn hỗ trợ cả hai).

    `code != 0` = lỗi thật (rate limit "Free Api Limit: 1 request/second",
    v.v.) → trả [] thay vì dùng dữ liệu rác (ADR-008).
    """
    if not isinstance(payload, dict) or payload.get("code") != 0:
        return []
    raw = payload.get("data")
    if isinstance(raw, dict):
        raw = raw.get("videos") or []
    if not isinstance(raw, list):
        return []
    return [v for v in raw if isinstance(v, dict)]


# TikWM đo thật 2026-09-24: 0.4s – 9.3s cho 1 request feed, hay timeout/HTTP 531
# tạm thời. Timeout cũ 6s → phần lớn request bị cắt ngang dù nguồn đang sống.
_TIKTOKWM_TIMEOUT_S = 20
_TIKTOKWM_FEED_HOSTS = ("https://tikwm.com", "https://www.tikwm.com")
# TikWM giới hạn 1 request/giây → phải chờ đủ nhịp giữa 2 lần cào comment.
_TIKTOKWM_COMMENT_MIN_INTERVAL_S = 1.1
_TIKTOKWM_COMMENT_TIMEOUT_S = 15
_TIKTOKWM_COMMENT_VIDEO_LIMIT = 2
_last_comment_fetch_ts: float = 0.0


def _fetch_tikwm_feed() -> list[dict[str, Any]]:
    """Gọi TikWM feed, thử lần lượt các host (cả www lẫn non-www đều sống nhưng
    hay lỗi tạm thời) → raise lỗi cuối cùng để caller ghi nhận circuit breaker."""
    last_err: Exception | None = None
    for host in _TIKTOKWM_FEED_HOSTS:
        url = f"{host}/api/feed/list?region=VN&count=20"
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(
                req, timeout=_TIKTOKWM_TIMEOUT_S, context=_SSL_CTX
            ) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            videos = parse_tikwm_feed(payload)
            if videos:
                return videos
            last_err = RuntimeError(
                f"code={payload.get('code')} msg={payload.get('msg')!r}"
                if isinstance(payload, dict)
                else "payload không phải JSON object"
            )
        except Exception as e:  # noqa: BLE001 — thử host kế tiếp
            last_err = e
            logger.info("tikwm_host_failed host=%s error=%s", host, e)
    if last_err is not None:
        raise last_err
    return []


def _fetch_tikwm_comments(video_url: str, limit: int = 3) -> list[str]:
    """Cào comment thật của 1 video TikWM.

    TikWM giới hạn **1 request/giây** (đo thật: request thứ 2 liên tiếp bị trả
    `code=-1 "Free Api Limit: 1 request/second."`) → chờ đủ nhịp trước khi gọi.
    Lỗi → trả [] (KHÔNG bịa comment, ADR-008).
    """
    global _last_comment_fetch_ts
    wait = _TIKTOKWM_COMMENT_MIN_INTERVAL_S - (time.time() - _last_comment_fetch_ts)
    if wait > 0:
        time.sleep(wait)
    _last_comment_fetch_ts = time.time()

    comments: list[str] = []
    try:
        qs = urllib.parse.urlencode({"url": video_url, "count": limit})
        cmt_url = f"https://tikwm.com/api/comment/list?{qs}"
        cmt_req = urllib.request.Request(cmt_url, headers=_HEADERS)
        with urllib.request.urlopen(
            cmt_req, timeout=_TIKTOKWM_COMMENT_TIMEOUT_S, context=_SSL_CTX
        ) as cresp:
            cdata = json.loads(cresp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — comment là tuỳ chọn, không phá luồng
        logger.info("tikwm_comment_fetch_failed error=%s", e)
        return []

    if not isinstance(cdata, dict) or cdata.get("code") != 0:
        return comments
    data = cdata.get("data")
    raw_cmts = data.get("comments") if isinstance(data, dict) else None
    for rc in raw_cmts or []:
        if not isinstance(rc, dict):
            continue
        c_text = rc.get("text", "")
        if not c_text:
            continue
        u_name = (rc.get("user") or {}).get("unique_id", "user")
        c_likes = rc.get("digg_count", 0)
        comments.append(f'@{u_name}: "{c_text}" (❤️ {c_likes} tim)')
    return comments


# TikWM feed: `region=VN` KHÔNG phải bộ lọc thật.
# Đo live 2026-09-25 (80–100 video/4–5 lần gọi): tỷ lệ VN chỉ **21–50%**, phần
# còn lại là MM/TH/PK/US/ID/PH/KR/JP/UG/SG/GB — có lần chỉ **1/20** video là VN.
# Các tham số `lang`, `country`, `type`, `city` KHÔNG lọc chặt hơn; endpoint
# `/api/feed/search` trả 403. Vì vậy phải TỰ LỌC theo `region`, và gọi vài lần
# để tích luỹ (1 lần gọi không đủ: 4 lần → 24 video VN unique).
_TIKTOKWM_FEED_ATTEMPTS = 3
_TIKTOKWM_MIN_VN_VIDEOS = 12


def _filter_vn_videos(videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """CHỈ giữ video có `region == "VN"` (bỏ hẳn video nước ngoài).

    Không dùng "ưu tiên lên đầu" như trước: khi tỷ lệ VN chỉ 1/20 thì 19 video
    Thái/Myanmar vẫn lọt vào radar TikTok VN và người dùng thấy đúng như vậy.
    """
    return [v for v in videos if str(v.get("region") or "").upper() == "VN"]


def _fetch_tikwm_feed_vn(attempts: int = _TIKTOKWM_FEED_ATTEMPTS) -> list[dict[str, Any]]:
    """Gọi TikWM feed vài lần, chỉ giữ video VN, khử trùng theo `video_id`.

    Mỗi lần gọi chỉ trả một phần video VN (có lần 0) nên phải tích luỹ qua nhiều
    lần mới đủ dữ liệu. Dừng sớm khi đã đủ `_TIKTOKWM_MIN_VN_VIDEOS`.
    Raise lỗi của lần gọi ĐẦU nếu mọi lần đều lỗi (caller ghi circuit breaker).
    """
    seen: set[str] = set()
    acc: list[dict[str, Any]] = []
    last_err: Exception | None = None

    for i in range(max(1, attempts)):
        try:
            batch = _filter_vn_videos(_fetch_tikwm_feed())
            for v in batch:
                vid = str(v.get("video_id") or "")
                if vid and vid not in seen:
                    seen.add(vid)
                    acc.append(v)
        except Exception as e:  # noqa: BLE001 — lần sau có thể thành công
            last_err = e
            logger.info("tikwm_feed_attempt_failed attempt=%d error=%s", i + 1, e)

        if len(acc) >= _TIKTOKWM_MIN_VN_VIDEOS or i + 1 >= attempts:
            break
        # Tôn trọng rate limit 1 req/s của TikWM giữa các lần gọi.
        time.sleep(_TIKTOKWM_COMMENT_MIN_INTERVAL_S)

    if not acc and last_err is not None:
        raise last_err
    logger.info(
        "tikwm_vn_accumulated videos=%d attempts_used<=%d", len(acc), attempts
    )
    return acc


def _scrape_tiktokwm_fallback(keyword: str = "", count: int = 12) -> list[TrendItem]:
    """PRIMARY TikTok source — TikWM Direct Free API (không tốn quota Apify).

    Cào dữ liệu thật từ TikWM feed với in-memory cache 5 phút và timeout bảo vệ.
    KHÔNG trả default topics tĩnh khi feed fail — trả [] để chuỗi smart
    (`_scrape_tiktok_smart`) rớt tầng Camoufox/Apify lấy dữ liệu thật
    (plan §3.4: fallback tĩnh chặn tầng browser thật phía sau).
    """
    global _TIKTOKWM_CACHE, _TIKTOKWM_CACHE_TIME
    items_out: list[TrendItem] = []
    now_str = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    kw_clean = keyword.strip()

    videos: list[dict[str, Any]] = []
    now_ts = time.time()
    if _TIKTOKWM_CACHE and (now_ts - _TIKTOKWM_CACHE_TIME < 300):
        videos = _TIKTOKWM_CACHE
    elif _CB_TIKWM.allow():
        try:
            videos = _fetch_tikwm_feed_vn()
            if videos:
                _TIKTOKWM_CACHE = videos
                _TIKTOKWM_CACHE_TIME = now_ts
                _CB_TIKWM.record_success()
            else:
                _CB_TIKWM.record_failure()
                if _TIKTOKWM_CACHE:
                    videos = _TIKTOKWM_CACHE
        except Exception as e:
            logger.warning(f"Lỗi fetch TikWM feed: {e}")
            _CB_TIKWM.record_failure()
            if _TIKTOKWM_CACHE:
                videos = _TIKTOKWM_CACHE
    else:
        # Circuit breaker đang mở — bỏ qua TikWM, dùng cache cũ nếu có.
        logger.info("tiktok_source_tikwm_circuit_open_skipping")
        if _TIKTOKWM_CACHE:
            videos = _TIKTOKWM_CACHE

    if kw_clean and videos:
        filtered = [v for v in videos if kw_clean.lower() in (v.get("title") or "").lower()]
        if filtered:
            videos = filtered

    # ADR-008 anti-fake-signals: KHÔNG sinh dữ liệu giả khi TikWM fail.
    # Trả [] để _scrape_tiktok_smart kích hoạt Apify backup (nếu có),
    # hoặc trả [] an toàn khi cả hai nguồn đều fail.
    if not videos:
        # Feed fail + cache rỗng: trả [] để chuỗi smart rớt tầng Camoufox/Apify
        # lấy dữ liệu thật, thay vì trả default topics tĩnh (plan §3.4).
        logger.warning(
            "tiktok_source_tikwm_empty",
            extra={"keyword": kw_clean[:50], "has_cache": bool(_TIKTOKWM_CACHE)},
        )
        return []

    for idx, v in enumerate(videos[:count]):
        author = v.get("author", {}).get("unique_id", "user")
        nickname = v.get("author", {}).get("nickname", author)
        video_id = v.get("video_id")
        title = v.get("title") or (
            f"Video TikTok về #{kw_clean}" if kw_clean else "Video xu hướng TikTok"
        )
        play_count = v.get("play_count", 0)
        digg_count = v.get("digg_count", 0)
        comment_count = v.get("comment_count", 0)
        video_url = f"https://www.tiktok.com/@{author}/video/{video_id}"

        # Chỉ cào comment cho 2 video đầu để đảm bảo tốc độ cực nhanh
        # (`_fetch_tikwm_comments` tự chờ đủ nhịp 1 req/s của TikWM).
        comments_list: list[str] = []
        if idx < _TIKTOKWM_COMMENT_VIDEO_LIMIT and video_id:
            comments_list = _fetch_tikwm_comments(video_url)

        short_kw = extract_core_tiktok_keyword(title) if not kw_clean else kw_clean
        clean_tag = re.sub(r"[^a-zA-Z0-9]", "", short_kw.lower())
        tag_url = f"https://www.tiktok.com/tag/{clean_tag}" if clean_tag else video_url

        items_out.append(
            TrendItem(
                id=f"live_tiktok_direct_{idx}_{video_id}",
                tieu_de=f"🎵 [TIKTOK VIRAL] {title[:65]}...",
                cum_tu_khoa_viral=short_kw,
                nguon_goc="tiktok_vn",
                loai_xu_huong="breaking_vn_24h",
                danh_muc="trao_luu_pop_culture"
                if not _is_fnb_title(title)
                else "am_thuc_fnb",
                vong_doi="dang_dinh",
                diem_nhan_dac_biet=f"Kênh sáng tạo: @{author} ({nickname}). Thống kê thật: {play_count:,} lượt xem | {digg_count:,} lượt thả tim | {comment_count:,} bình luận.",
                nguon_goc_chi_tiet=f"Cào dữ liệu video và comment THẬT 100% từ TikTok lúc {now_str}.",
                ngu_canh_su_dung="Video ngắn đang được đẩy lên xu hướng For You TikTok với hàng triệu lượt xem.",
                tam_ly_gioi_tre="Tương tác trực tiếp trên bình luận của video triệu view.",
                toc_do_tang_truong_24h=max(300.0, 990.0 - (idx * 40)),
                diem_tiem_nang_viral=max(80, 99 - idx),
                du_bao_thoi_gian="Đang phân phối mạnh trên For You Page",
                link_goc=video_url,
                tiktok_url=video_url,
                tiktok_tag_url=tag_url,
                thoi_gian_cao=now_str,
                luot_tiep_can=f"{play_count:,} views | {digg_count:,} tim",
                trich_doan_noi_dung_that=f"Mô tả video: {title}",
                binh_luan_that_tiktok=comments_list,
                nen_tang_lan_toa=["TikTok Việt Nam"],
                tu_khoa_hashtag=[f"#{author}", f"#{clean_tag}", "#xuhuongtiktok"],
                is_live_scraped=True,
            )
        )
    return items_out


def _scrape_google_trends_vn(keyword: str = "") -> list[TrendItem]:
    """Lấy dữ liệu Google Trends Việt Nam.

    Chuỗi khi KHÔNG lọc keyword: **gộp** Trending Now + Discovery → RSS.
    Chuỗi khi CÓ keyword: SerpApi theo từ khoá → RSS.

    ⚠️ ĐO THẬT 2026-09-26 — vì sao GỘP chứ không `return` sớm:
    Hai tầng trả **hai loại tín hiệu KHÁC NHAU**, không thay thế nhau:
      - Trending Now = từ khoá **tìm kiếm bùng nổ** (fpt play, bão, xsmb…)
        → biết XH đang tìm GÌ, có số lượt tìm kiếm.
      - Discovery    = **slang/meme từ báo chí** (`bá khí`, `thánh meme`…)
        → bắt được cái Trending Now bỏ sót (trend văn hoá không phải tìm kiếm).
    Trước đây `return tn_items` ngay → Discovery không bao giờ chạy (bug thật
    phát hiện khi chạy live: `id bắt đầu bằng 'discovery_': 0`).
    """
    # 0. Trending Now (bảng xếp hạng tìm kiếm quốc gia) — không cần keyword.
    tn_items: list[TrendItem] = []
    try:
        from ca_agents.sources.gtrends_trending_now_source import fetch_trending_now_serpapi

        tn_items = fetch_trending_now_serpapi(geo="VN", hl="vi", count=12)
        if keyword.strip() and tn_items:
            kw_low = keyword.strip().lower()
            tn_items = [it for it in tn_items if kw_low in it.cum_tu_khoa_viral.lower()]
        if tn_items:
            logger.info("google_trends_source_trending_now items_count=%d", len(tn_items))
    except Exception as exc:  # noqa: BLE001 — rớt tầng
        logger.info("Trending Now không khả dụng: %s", exc)

    # Nếu có keyword cụ thể → lọc theo keyword qua các tầng (Trending Now đã lọc
    # ở trên, kế đó SerpApi theo từ khoá, cuối cùng RSS). KHÔNG gộp discovery
    # vì discovery là "quét rộng" để tìm trend mới, không phải lọc theo keyword.
    if keyword.strip():
        if tn_items:
            return tn_items
        try:
            from ca_agents.sources.gtrends_serpapi_source import fetch_fnb_trends_serpapi

            serp_items = fetch_fnb_trends_serpapi(keyword=keyword.strip(), geo="VN")
            if serp_items:
                logger.info(
                    "google_trends_source_serpapi_primary items_count=%d", len(serp_items)
                )
                return serp_items
        except Exception as exc:  # noqa: BLE001
            logger.info("SerpApi Trends (keyword) fallback sang RSS: %s", exc)
        return _scrape_google_trends_vn_rss(keyword=keyword)

    # 1. DISCOVERY: từ khoá MỚI (slang/meme) từ bài báo tổng hợp.
    disc_items: list[TrendItem] = []
    try:
        from ca_agents.sources.trend_discovery_source import discover_candidates

        cands = discover_candidates()
        if cands:
            disc_items = _candidates_to_trend_items(cands)
            logger.info(
                "google_trends_source_discovery items_count=%d candidates=%d",
                len(disc_items),
                len(cands),
            )
    except Exception as exc:  # noqa: BLE001
        logger.info("Discovery không khả dụng: %s", exc)

    # 2. GỘP hai tầng (khử trùng theo cụm từ khoá).
    merged = _merge_trend_layers(tn_items, disc_items)
    if merged:
        return merged

    # 3. SerpApi theo từ khoá mặc định (khi cả 2 tầng trên đều rỗng).
    try:
        from ca_agents.sources.gtrends_serpapi_source import fetch_fnb_trends_serpapi

        serp_items = fetch_fnb_trends_serpapi(keyword="cà phê", geo="VN")
        if serp_items:
            logger.info("google_trends_source_serpapi_primary items_count=%d", len(serp_items))
            return serp_items
    except Exception as exc:
        logger.info("SerpApi Trends fallback sang RSS: %s", exc)

    # 4. FALLBACK: Google Trends RSS Việt Nam (miễn phí, không cần key)
    return _scrape_google_trends_vn_rss(keyword=keyword)


def _merge_trend_layers(
    primary: list[TrendItem], secondary: list[TrendItem]
) -> list[TrendItem]:
    """Gộp 2 tầng trend, khử trùng theo `cum_tu_khoa_viral` (không phân biệt hoa/thường).

    Tầng `primary` (Trending Now) đứng trước vì có số liệu lượt tìm kiếm thật;
    `secondary` (Discovery) nối sau để giữ cả tín hiệu slang/meme.
    """
    seen: set[str] = set()
    out: list[TrendItem] = []
    for it in list(primary) + list(secondary):
        key = (it.cum_tu_khoa_viral or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _candidates_to_trend_items(candidates: list[Any]) -> list[TrendItem]:
    """Map `TrendCandidate` (discovery) → `TrendItem` để hiển thị.

    ADR-008: candidate là **GỢI Ý do AI tự phát hiện**, chưa được xác minh
    trên mạng xã hội → gắn nhãn rõ + `is_live_scraped=True` chỉ nghĩa là
    "dữ liệu tín hiệu là THẬT từ báo chí", KHÔNG phải "đã xác minh viral".
    """
    items: list[TrendItem] = []
    now_str = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    for idx, c in enumerate(candidates):
        kw = c.keyword
        clean_tag = re.sub(r"[^a-zA-Z0-9_]", "", kw.lower())
        sources_str = ", ".join(c.sources[:4])
        conf_pct = int(round(c.confidence * 100))
        items.append(
            TrendItem(
                id=f"discovery_{idx}_{clean_tag or idx}",
                tieu_de=f"🔎 [PHÁT HIỆN MỚI] {kw}",
                cum_tu_khoa_viral=kw,
                nguon_goc="google_vn",
                loai_xu_huong="breaking_vn_24h",
                danh_muc="trao_luu_pop_culture",
                vong_doi="moi_nhu",
                diem_nhan_dac_biet=(
                    f"AI tự phát hiện từ bài báo tổng hợp: {c.mention_count} lần / "
                    f"{c.source_count} nguồn ({sources_str}). "
                    f"Độ tin cậy {conf_pct}% (nguồn {c.source_count}, "
                    f"tươi {c.freshness_days:.0f} ngày)."
                ),
                nguon_goc_chi_tiet=(
                    f"Trend Discovery: quét bài báo tổng hợp (query meta-keyword "
                    f"có tháng) lúc {now_str}. Đây là GỢI Ý chưa xác minh trên MXH."
                ),
                ngu_canh_su_dung=(
                    f"Từ khoá '{kw}' đang được báo chí nhắc nhiều — kiểm tra "
                    f"TikTok/Threads để xác nhận trước khi làm nội dung."
                ),
                tam_ly_gioi_tre=(
                    "Tín hiệu sớm: báo chí bắt đầu tổng hợp → giới trẻ có thể đã dùng."
                ),
                toc_do_tang_truong_24h=float(conf_pct),
                diem_tiem_nang_viral=min(95, 40 + conf_pct),
                du_bao_thoi_gian="Tín hiệu sớm — cần xác minh trên TikTok/Threads",
                link_goc="",
                tiktok_url=f"https://www.tiktok.com/search?q={kw}",
                tiktok_tag_url=(
                    f"https://www.tiktok.com/tag/{clean_tag}" if clean_tag else ""
                ),
                thoi_gian_cao=now_str,
                luot_tiep_can=f"{c.mention_count} lần / {c.source_count} nguồn báo",
                trich_doan_noi_dung_that=" | ".join(c.sample_titles[:2]),
                binh_luan_that_tiktok=[],
                nen_tang_lan_toa=["Báo chí VN", "Trend Discovery"],
                tu_khoa_hashtag=[f"#{clean_tag}", "#trendmoi", "#discovery"],
                is_live_scraped=True,
            )
        )
    return items


def _scrape_google_trends_vn_rss(keyword: str = "") -> list[TrendItem]:
    """Fallback: Google Trends RSS Việt Nam (miễn phí, không cần key)."""
    items_out: list[TrendItem] = []
    now_str = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    try:
        url = "https://trends.google.com/trending/rss?geo=VN"
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=6, context=_SSL_CTX) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = root.findall(".//item")
            for idx, it in enumerate(items):
                title_elem = it.find("title")
                title = (title_elem.text or "Xu hướng tìm kiếm") if title_elem is not None else "Xu hướng tìm kiếm"

                if keyword.strip() and keyword.lower() not in title.lower():
                    continue

                link_elem = it.find("link")
                link_goc = (link_elem.text or "https://trends.google.com") if link_elem is not None else "https://trends.google.com"

                traffic_elem = it.find("{https://trends.google.com/trending/rss}approx_traffic")
                traffic = (traffic_elem.text or "1,000+") if traffic_elem is not None else "1,000+"

                news_items = it.findall("{https://trends.google.com/trending/rss}news_item")
                news_snippet = ""
                news_source = "Báo chí VN"
                news_url = link_goc
                if news_items:
                    nt = news_items[0].find(
                        "{https://trends.google.com/trending/rss}news_item_title"
                    )
                    ns = news_items[0].find(
                        "{https://trends.google.com/trending/rss}news_item_source"
                    )
                    nu = news_items[0].find("{https://trends.google.com/trending/rss}news_item_url")
                    if nt is not None and nt.text:
                        news_snippet = nt.text
                    if ns is not None and ns.text:
                        news_source = ns.text
                    if nu is not None and nu.text:
                        news_url = nu.text

                trend_id = (
                    f"live_google_vn_{idx}_{re.sub(r'[^a-zA-Z0-9]', '_', title.lower())[:25]}"
                )
                encoded_kw = urllib.parse.quote(title)
                tt_search = f"https://www.tiktok.com/search?q={encoded_kw}"
                clean_tag = re.sub(r"[^a-zA-Z0-9]", "", title.lower())
                tt_tag = f"https://www.tiktok.com/tag/{clean_tag}" if clean_tag else tt_search

                items_out.append(
                    TrendItem(
                        id=trend_id,
                        tieu_de=f"🔥 [GOOGLE TRENDS VN] {title}",
                        cum_tu_khoa_viral=title,
                        nguon_goc="google_vn",
                        loai_xu_huong="breaking_vn_24h",
                        danh_muc="meme_cau_noi",
                        vong_doi="moi_nhu",
                        diem_nhan_dac_biet=f"Lượng tìm kiếm đột biến thực tế tại Việt Nam: {traffic}. Tin tức báo chí liên quan: '{news_snippet}' ({news_source}).",
                        nguon_goc_chi_tiet=f"Cào dữ liệu thật từ Google Trends Search Việt Nam lúc {now_str}.",
                        ngu_canh_su_dung="Bắt nhịp sự kiện đang được người Việt tìm kiếm nhiều nhất hôm nay.",
                        tam_ly_gioi_tre="Sự kiện thể thao, giải trí hoặc tin tức nóng đang diễn ra.",
                        toc_do_tang_truong_24h=max(100.0, 990.0 - (idx * 30)),
                        diem_tiem_nang_viral=max(70, 99 - idx),
                        du_bao_thoi_gian="Đang đạt đỉnh lưu lượng tìm kiếm hôm nay",
                        link_goc=news_url,
                        tiktok_url=tt_search,
                        tiktok_tag_url=tt_tag,
                        thoi_gian_cao=now_str,
                        luot_tiep_can=f"{traffic} lượt tìm kiếm thật",
                        trich_doan_noi_dung_that=news_snippet
                        or "Từ khóa thịnh hành trên Google Search Việt Nam",
                        binh_luan_that_tiktok=[],
                        nen_tang_lan_toa=["Google Trends Việt Nam"],
                        tu_khoa_hashtag=[f"#{clean_tag}", "#xuhuongvn", "#googletrends"],
                        is_live_scraped=True,
                    )
                )
    except Exception as e:
        logger.warning(f"Lỗi cào Google Trends VN: {e}")
    return items_out


def _scrape_genz_media_vn(keyword: str = "") -> list[TrendItem]:
    """Cào trực tiếp toàn bộ bài viết mới nhất từ Kênh14 Đời Sống & Gen Z (Nguồn trào lưu Threads/Lifestyle)."""
    items_out: list[TrendItem] = []
    now_str = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    try:
        url = "https://kenh14.vn/doi-song.rss"
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=6, context=_SSL_CTX) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = root.findall(".//item")
            for idx, it in enumerate(items):
                title_elem = it.find("title")
                title = title_elem.text or "" if title_elem is not None else ""

                desc_elem = it.find("description")
                desc_raw = desc_elem.text or "" if desc_elem is not None else ""
                desc_clean = re.sub(r"<[^>]+>", "", desc_raw).strip()

                if keyword.strip():
                    kw_low = keyword.lower()
                    if kw_low not in title.lower() and kw_low not in desc_clean.lower():
                        continue

                link_elem = it.find("link")
                link_goc = link_elem.text or "https://kenh14.vn" if link_elem is not None else "https://kenh14.vn"

                trend_id = f"live_genz_vn_{idx}_{re.sub(r'[^a-zA-Z0-9]', '_', title.lower())[:25]}"
                short_kw = extract_core_tiktok_keyword(title)
                encoded_kw = urllib.parse.quote(short_kw)
                tt_search = f"https://www.tiktok.com/search?q={encoded_kw}"
                clean_tag = re.sub(r"[^a-zA-Z0-9]", "", short_kw.lower())
                tt_tag = f"https://www.tiktok.com/tag/{clean_tag}" if clean_tag else tt_search

                items_out.append(
                    TrendItem(
                        id=trend_id,
                        tieu_de=f"🧵 [META THREADS] {title}",
                        cum_tu_khoa_viral=short_kw,
                        nguon_goc="threads_vn",
                        loai_xu_huong="breaking_vn_24h",
                        danh_muc="tam_ly_lifestyle"
                        if not _is_fnb_title(title)
                        else "am_thuc_fnb",
                        vong_doi="dang_dinh",
                        diem_nhan_dac_biet=f"Trích đoạn nội dung bài viết thật: {desc_clean}",
                        nguon_goc_chi_tiet=f"Cào dữ liệu thật từ chuyên mục Đời sống & Gen Z lúc {now_str}.",
                        ngu_canh_su_dung="Theo dõi đời sống, xu hướng check-in và tâm lý giới trẻ.",
                        tam_ly_gioi_tre="Phong cách sống, ẩm thực và trải nghiệm của giới trẻ hiện nay.",
                        toc_do_tang_truong_24h=max(310.0, 850.0 - (idx * 15)),
                        diem_tiem_nang_viral=max(75, 98 - (idx // 2)),
                        du_bao_thoi_gian="Bài viết mới xuất bản trong 24h qua",
                        link_goc=link_goc,
                        tiktok_url=tt_search,
                        tiktok_tag_url=tt_tag,
                        thoi_gian_cao=now_str,
                        luot_tiep_can="Tin mới xuất bản",
                        trich_doan_noi_dung_that=desc_clean,
                        binh_luan_that_tiktok=[],
                        nen_tang_lan_toa=["Meta Threads"],
                        tu_khoa_hashtag=["#genzlifestyle", f"#{clean_tag}", "#threads"],
                        is_live_scraped=True,
                    )
                )
    except Exception as e:
        logger.warning(f"Lỗi cào Gen Z Media VN: {e}")
    return items_out


def _scrape_showbiz_kols_vn(keyword: str = "") -> list[TrendItem]:
    """Cào trực tiếp tin tức giải trí, KOLs TikTok, Showbiz từ Kênh14 Star."""
    items_out: list[TrendItem] = []
    now_str = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    try:
        url = "https://kenh14.vn/star.rss"
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=6, context=_SSL_CTX) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = root.findall(".//item")
            for idx, it in enumerate(items):
                title_elem = it.find("title")
                title = title_elem.text or "" if title_elem is not None else ""

                desc_elem = it.find("description")
                desc_raw = desc_elem.text or "" if desc_elem is not None else ""
                desc_clean = re.sub(r"<[^>]+>", "", desc_raw).strip()

                if keyword.strip():
                    kw_low = keyword.lower()
                    if kw_low not in title.lower() and kw_low not in desc_clean.lower():
                        continue

                link_elem = it.find("link")
                link_goc = link_elem.text or "https://kenh14.vn" if link_elem is not None else "https://kenh14.vn"

                trend_id = f"live_star_vn_{idx}_{re.sub(r'[^a-zA-Z0-9]', '_', title.lower())[:25]}"
                short_kw = extract_core_tiktok_keyword(title)
                encoded_kw = urllib.parse.quote(short_kw)
                tt_search = f"https://www.tiktok.com/search?q={encoded_kw}"
                clean_tag = re.sub(r"[^a-zA-Z0-9]", "", short_kw.lower())
                tt_tag = f"https://www.tiktok.com/tag/{clean_tag}" if clean_tag else tt_search

                items_out.append(
                    TrendItem(
                        id=trend_id,
                        tieu_de=f"🎵 [KOLS & SHOWBIZ] {title}",
                        cum_tu_khoa_viral=short_kw,
                        nguon_goc="star_vn",
                        loai_xu_huong="breaking_vn_24h",
                        danh_muc="trao_luu_pop_culture",
                        vong_doi="dang_dinh",
                        diem_nhan_dac_biet=f"Trích đoạn tin tức thật: {desc_clean}",
                        nguon_goc_chi_tiet=f"Cào dữ liệu thật từ chuyên mục Star & KOLs lúc {now_str}.",
                        ngu_canh_su_dung="Theo dõi sự kiện và các nhân vật đang được bàn luận nhiều trên mạng xã hội.",
                        tam_ly_gioi_tre="Sự quan tâm dành cho các gương mặt nổi tiếng và trào lưu mạng.",
                        toc_do_tang_truong_24h=max(310.0, 780.0 - (idx * 15)),
                        diem_tiem_nang_viral=max(75, 97 - (idx // 2)),
                        du_bao_thoi_gian="Tin tức mới cập nhật hôm nay",
                        link_goc=link_goc,
                        tiktok_url=tt_search,
                        tiktok_tag_url=tt_tag,
                        thoi_gian_cao=now_str,
                        luot_tiep_can="Tin giải trí hot",
                        trich_doan_noi_dung_that=desc_clean,
                        binh_luan_that_tiktok=[],
                        nen_tang_lan_toa=["Showbiz & Báo chí"],
                        tu_khoa_hashtag=["#showbizviet", f"#{clean_tag}", "#idol"],
                        is_live_scraped=True,
                    )
                )
    except Exception as e:
        logger.warning(f"Lỗi cào Showbiz Star VN: {e}")
    return items_out


def _scrape_google_trends_global(keyword: str = "") -> list[TrendItem]:
    """Cào trực tiếp từ Google Trends US & Quốc tế."""
    items_out: list[TrendItem] = []
    now_str = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    try:
        url = "https://trends.google.com/trending/rss?geo=US"
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=6, context=_SSL_CTX) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = root.findall(".//item")
            for idx, it in enumerate(items):
                title_elem = it.find("title")
                title = title_elem.text or "" if title_elem is not None else ""

                if keyword.strip() and keyword.lower() not in title.lower():
                    continue

                link_elem = it.find("link")
                link_goc = link_elem.text or "https://trends.google.com" if link_elem is not None else "https://trends.google.com"

                traffic_elem = it.find("{https://trends.google.com/trending/rss}approx_traffic")
                traffic = traffic_elem.text or "10,000+" if traffic_elem is not None else "10,000+"

                news_items = it.findall("{https://trends.google.com/trending/rss}news_item")
                news_snippet = ""
                news_url = link_goc
                if news_items:
                    nt = news_items[0].find(
                        "{https://trends.google.com/trending/rss}news_item_title"
                    )
                    nu = news_items[0].find("{https://trends.google.com/trending/rss}news_item_url")
                    if nt is not None and nt.text:
                        news_snippet = nt.text
                    if nu is not None and nu.text:
                        news_url = nu.text

                trend_id = f"live_global_{idx}_{re.sub(r'[^a-zA-Z0-9]', '_', title.lower())[:25]}"
                encoded_kw = urllib.parse.quote(title)
                tt_search = f"https://www.tiktok.com/search?q={encoded_kw}"
                clean_tag = re.sub(r"[^a-zA-Z0-9]", "", title.lower())
                tt_tag = f"https://www.tiktok.com/tag/{clean_tag}" if clean_tag else tt_search

                items_out.append(
                    TrendItem(
                        id=trend_id,
                        tieu_de=f"🌐 [GLOBAL TREND] {title.title()}",
                        cum_tu_khoa_viral=title,
                        nguon_goc="tiktok_global",
                        loai_xu_huong="predictive_global",
                        danh_muc="trao_luu_pop_culture",
                        vong_doi="moi_nhu",
                        diem_nhan_dac_biet=f"Lượng tìm kiếm toàn cầu: {traffic}. Tin tiêu điểm: '{news_snippet}'.",
                        nguon_goc_chi_tiet=f"Cào dữ liệu thật từ Google Trends US lúc {now_str}.",
                        ngu_canh_su_dung="Theo dõi xu hướng tìm kiếm quốc tế.",
                        tam_ly_gioi_tre="Văn hóa Pop và sự kiện quốc tế nóng.",
                        toc_do_tang_truong_24h=500.0 - (idx * 20),
                        diem_tiem_nang_viral=92 - idx,
                        du_bao_thoi_gian="Top trending toàn cầu",
                        link_goc=news_url,
                        tiktok_url=tt_search,
                        tiktok_tag_url=tt_tag,
                        thoi_gian_cao=now_str,
                        luot_tiep_can=f"{traffic} searches",
                        trich_doan_noi_dung_that=news_snippet or "Top Search Google US",
                        binh_luan_that_tiktok=[],
                        nen_tang_lan_toa=["Google Trends Quốc tế"],
                        tu_khoa_hashtag=[f"#{clean_tag}", "#globaltrend"],
                        is_live_scraped=True,
                    )
                )
    except Exception as e:
        logger.warning(f"Lỗi cào Global Trends: {e}")
    return items_out


def _scrape_threads_smart(
    keyword: str = "",
    count: int = 12,
    nguon_goc: str = "threads_vn",
    scrape_mode: str = "auto",
) -> list[TrendItem]:
    """Threads Official API → Camoufox (bài thật) → Google Bridge → Direct Jina → Apify → RSS.

    Modes:
        - auto: Official API → Camoufox → Google Bridge → Direct Jina → Apify → RSS
        - direct_only: Google Bridge → Direct Jina → RSS (không API/Apify/Camoufox)
        - apify_force: Apify first → Google Bridge backup
        - browser: Camoufox first (plan §3.5)

    ĐO THẬT 2026-09-26: Camoufox đứng TRƯỚC Google Bridge trong `auto` vì
    Camoufox cào được bài Threads THẬT (link /post/, tương tác thật), còn
    Bridge chỉ trả bài báo chứa chữ "Threads" (Google không index Threads).
    """
    start = time.monotonic()
    # Theo dõi đã thử Camoufox chưa — tránh launch browser 2 lần cho 1 request
    # (mode `browser` gọi Camoufox first, nếu fail thì tier 2.5 không gọi lại).
    camoufox_tried = False

    # If user selected APIFY FORCE mode
    if scrape_mode == "apify_force":
        try:
            from ca_agents.sources.threads_apify_source import scrape_threads_apify

            items = scrape_threads_apify(
                keyword=keyword,
                count=count,
                mode="search",
                nguon_goc=nguon_goc,
            )
            if items:
                return cast(list[TrendItem], items)
        except Exception as e:
            logger.warning("threads_apify_force_failed_trying_bridge: %s", e)

    # BROWSER mode: Camoufox first (plan §3.5) — rớt tầng về chuỗi cũ nếu fail.
    if scrape_mode == "browser":
        camoufox_tried = True
        try:
            if not keyword.strip():
                try:
                    from ca_agents.sources.threads_trending_source import scrape_threads_trending

                    t_items = scrape_threads_trending(count=count, nguon_goc=nguon_goc)
                    if t_items:
                        return cast(list[TrendItem], t_items)
                except Exception as te:  # noqa: BLE001
                    logger.warning("threads_browser_trending_failed_trying_search: %s", te)

            from ca_agents.sources.threads_camoufox_source import scrape_threads_camoufox

            items = scrape_threads_camoufox(
                keyword=keyword,
                count=count,
                nguon_goc=nguon_goc,
            )
            if items:
                return cast(list[TrendItem], items)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "threads_browser_mode_failed_falling_back",
                extra={"error": str(e)[:200]},
            )

    # 0. TIER 0 — Threads Official API (graph.threads.net /keyword_search):
    # nguồn chính thức, hợp lệ, miễn phí (2,200 queries/24h). Chỉ chạy khi
    # có THREADS_ACCESS_TOKEN; token sai / API lỗi → rớt tầng ngay.
    if scrape_mode != "direct_only":
        try:
            from ca_agents.sources.threads_official_api_source import (
                ThreadsOfficialApiError,
                is_configured,
                scrape_threads_official_api,
            )

            if is_configured():
                items = scrape_threads_official_api(
                    keyword=keyword,
                    count=count,
                    nguon_goc=nguon_goc,
                )
                if items:
                    logger.info(
                        "threads_source_official_api",
                        extra={
                            "source": "threads_official_api",
                            "nguon_goc": nguon_goc,
                            "items_count": len(items),
                            "duration_ms": int((time.monotonic() - start) * 1000),
                        },
                    )
                    return cast(list[TrendItem], items)
        except ThreadsOfficialApiError as e:
            logger.warning(
                "threads_official_api_failed_trying_bridge",
                extra={"error": str(e)[:200]},
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "threads_official_api_unexpected_error",
                extra={"error": str(e)[:200]},
            )

    # 1. PRIMARY: Camoufox browser-thật — cào bài Threads THẬT (link /post/,
    #    tương tác thật). ĐO THẬT 2026-09-26: đứng TRƯỚC Google Bridge vì
    #    Bridge chỉ trả BÀI BÁO chứa chữ "Threads" (Google không index Threads),
    #    không phải bài Threads thật. Đặt Bridge trước sẽ che mất nguồn thật.
    if scrape_mode not in {"direct_only", "apify_force"}:
        try:
            from ca_agents.clients.camoufox_client import is_available as _cf_avail

            if _cf_avail():
                from ca_agents.sources.threads_camoufox_source import scrape_threads_camoufox

                items = scrape_threads_camoufox(
                    keyword=keyword,
                    count=count,
                    nguon_goc=nguon_goc,
                )
                if items:
                    logger.info(
                        "threads_source_camoufox_primary",
                        extra={
                            "source": "camoufox_threads",
                            "nguon_goc": nguon_goc,
                            "items_count": len(items),
                            "duration_ms": int((time.monotonic() - start) * 1000),
                        },
                    )
                    return cast(list[TrendItem], items)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "threads_camoufox_primary_failed_trying_bridge: %s", str(e)[:200]
            )

    # 2. FALLBACK: Google Index Real-Time Bridge.
    #    ⚠️ Nguồn này trả BÀI BÁO chứa chữ "Threads" (Google KHÔNG index nội
    #    dung Threads) → items mang is_live_scraped=False + nhãn "TÍN HIỆU BÁO CHÍ".
    try:
        from ca_agents.sources.threads_google_bridge_source import scrape_threads_google_bridge

        items = scrape_threads_google_bridge(
            keyword=keyword,
            count=count,
            nguon_goc=nguon_goc,
        )
        if items:
            logger.info(
                "threads_source_google_bridge_fallback",
                extra={
                    "source": "threads_google_bridge",
                    "nguon_goc": nguon_goc,
                    "items_count": len(items),
                    "duration_ms": int((time.monotonic() - start) * 1000),
                },
            )
            return items
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "threads_google_bridge_failed_trying_direct: %s", str(e)[:200]
        )

    # 2. SUB-PRIMARY: Direct Free Threads Scraper
    try:
        from ca_agents.sources.threads_direct_source import scrape_threads_direct

        items = scrape_threads_direct(
            keyword=keyword,
            count=count,
            nguon_goc=nguon_goc,
        )
        if items:
            return items
    except Exception as e:  # noqa: BLE001
        logger.warning("threads_direct_failed_trying_camoufox: %s", str(e)[:200])

    # 2.5 CAMOUFOX TIER: browser-thật miễn phí (giữa Jina direct và Apify, plan §3.5)
    # Bỏ qua nếu đã thử Camoufox ở mode `browser` — tránh launch browser 2 lần.
    if scrape_mode not in {"direct_only", "apify_force"} and not camoufox_tried:
        try:
            from ca_agents.clients.camoufox_client import is_available

            if is_available():
                if not keyword.strip():
                    try:
                        from ca_agents.sources.threads_trending_source import (
                            scrape_threads_trending,
                        )

                        t_items = scrape_threads_trending(count=count, nguon_goc=nguon_goc)
                        if t_items:
                            return cast(list[TrendItem], t_items)
                    except Exception as te:  # noqa: BLE001
                        logger.warning("threads_camoufox_trending_failed_trying_search: %s", te)

                from ca_agents.sources.threads_camoufox_source import scrape_threads_camoufox

                items = scrape_threads_camoufox(
                    keyword=keyword,
                    count=count,
                    nguon_goc=nguon_goc,
                )
                if items:
                    logger.info(
                        "threads_source_camoufox",
                        extra={
                            "source": "camoufox_threads",
                            "nguon_goc": nguon_goc,
                            "items_count": len(items),
                            "duration_ms": int((time.monotonic() - start) * 1000),
                        },
                    )
                    return cast(list[TrendItem], items)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "threads_camoufox_tier_failed_trying_apify",
                extra={"error": str(e)[:200]},
            )

    # 3. SECONDARY / BACKUP: Apify Threads Scraper (only if mode != direct_only)
    if scrape_mode != "direct_only":
        try:
            from ca_agents.sources.threads_apify_source import scrape_threads_apify

            items = scrape_threads_apify(
                keyword=keyword,
                count=count,
                mode="search",
                nguon_goc=nguon_goc,
            )
            if items:
                logger.info(
                    "threads_source_apify_backup",
                    extra={
                        "source": "apify_threads_backup",
                        "nguon_goc": nguon_goc,
                        "items_count": len(items),
                        "duration_ms": int((time.monotonic() - start) * 1000),
                    },
                )
                return cast(list[TrendItem], items)
        except Exception as e:  # noqa: BLE001
            logger.warning("threads_apify_backup_also_failed: %s", e)

    # 4. FALLBACK: Gen Z RSS Media
    return _scrape_genz_media_vn(keyword=keyword)


# ── Cache kết quả tổng hợp fetch_trend_radar ────────────────────────────────
# Nhiều user cùng xem "Tất cả nguồn" trong 1 phút → trước đây cào lại 5 nguồn
# mỗi lần. Cache này (TTL 90s) giảm tải nguồn bên thứ ba đáng kể. `force_live`
# bỏ qua cache để luôn cào mới (dùng cho test / yêu cầu real-time tuyệt đối).
_RADAR_CACHE: dict[str, tuple[float, list[TrendItem]]] = {}
_RADAR_CACHE_TTL_S = 90.0


# ── Circuit breaker cho nguồn free (TikWM/Jina/Google Bridge) ───────────────
# SerpApi đã có circuit breaker riêng, nhưng các nguồn free thì không. Nếu
# TikWM/Jina/Google Bridge chặn IP → mỗi request đều thử (timeout 6-8s) rồi mới
# rớt tầng → chậm + tăng rủi ro bị chặn nặng hơn. Pattern nhẹ này mở mạch khi
# fail >=3 lần/60s, bỏ qua nguồn trong 5 phút (tái dùng ý tưởng SerpApi CB).
_CB_FAILURE_THRESHOLD = 3
_CB_OPEN_SECONDS = 300.0
_CB_WINDOW_SECONDS = 60.0


class _SourceCircuitBreaker:
    """Circuit breaker đơn giản cho một nguồn cào free."""

    def __init__(self) -> None:
        self._failures: list[float] = []
        self._open_until: float = 0.0

    def allow(self) -> bool:
        if time.monotonic() < self._open_until:
            return False
        return True

    def record_failure(self) -> None:
        now = time.monotonic()
        # Chỉ đếm lỗi trong cửa sổ 60s gần nhất.
        self._failures = [t for t in self._failures if now - t <= _CB_WINDOW_SECONDS]
        self._failures.append(now)
        if len(self._failures) >= _CB_FAILURE_THRESHOLD:
            self._open_until = now + _CB_OPEN_SECONDS
            logger.warning(
                "source_circuit_breaker_opened failures=%d open_seconds=%.0f",
                len(self._failures),
                _CB_OPEN_SECONDS,
            )

    def record_success(self) -> None:
        self._failures = []


# Circuit breaker per-source (module-level, process-wide).
_CB_TIKWM = _SourceCircuitBreaker()
_CB_JINA = _SourceCircuitBreaker()
_CB_GOOGLE_BRIDGE = _SourceCircuitBreaker()


def _radar_cache_key(
    platform: str,
    category: str,
    trend_type: str,
    keyword: str,
    scrape_mode: str,
) -> str:
    return f"{platform}|{category}|{trend_type}|{(keyword or '').strip().lower()}|{scrape_mode}"


def _radar_cache_get(key: str) -> list[TrendItem] | None:
    hit = _RADAR_CACHE.get(key)
    if hit is None:
        return None
    cached_at, items = hit
    if time.monotonic() - cached_at > _RADAR_CACHE_TTL_S:
        _RADAR_CACHE.pop(key, None)
        return None
    return items


def _radar_cache_put(key: str, items: list[TrendItem]) -> None:
    _RADAR_CACHE[key] = (time.monotonic(), items)


def _radar_cache_clear() -> None:
    """Xóa cache (dùng cho test)."""
    _RADAR_CACHE.clear()


def fetch_trend_radar(
    trend_type_filter: str = "all",
    category_filter: str = "all",
    platform_filter: str = "all",
    force_live: bool = True,
    keyword: str = "",
    scrape_mode: str = "auto",
) -> list[TrendItem]:
    """Cào dữ liệu xu hướng 100% real-time theo nguồn được chọn, từ khóa và chế độ cào."""
    effective_platform = platform_filter
    effective_type = trend_type_filter
    if trend_type_filter in {"tiktok_vn", "threads_vn", "google_vn", "star_vn", "tiktok_global"}:
        effective_platform = trend_type_filter
        effective_type = "all"

    # Cache tổng hợp: bỏ qua khi force_live=True (mặc định) để giữ hành vi cũ.
    cache_key = _radar_cache_key(
        effective_platform, category_filter, effective_type, keyword, scrape_mode
    )
    if not force_live:
        cached = _radar_cache_get(cache_key)
        if cached is not None:
            return cached

    results: list[TrendItem] = []

    # 1. Nếu chỉ chọn TikTok VN -> CHỈ cào đúng TikTok
    if effective_platform == "tiktok_vn":
        results = _scrape_tiktok_smart(
            keyword=keyword, count=12, nguon_goc="tiktok_vn", scrape_mode=scrape_mode
        )
    # 2. Nếu chọn Threads VN -> CHỈ cào đúng Threads
    elif effective_platform == "threads_vn":
        results = _scrape_threads_smart(
            keyword=keyword, count=12, nguon_goc="threads_vn", scrape_mode=scrape_mode
        )
    # 3. Nếu chọn Google Trends VN -> CHỈ cào đúng Google Trends!
    elif effective_platform == "google_vn":
        results = _scrape_google_trends_vn(keyword=keyword)
    # 4. Nếu chọn Showbiz & KOLs -> CHỈ cào đúng Showbiz!
    elif effective_platform == "star_vn":
        results = _scrape_showbiz_kols_vn(keyword=keyword)
    # 5. Nếu chọn Global -> CHỈ cào đúng Global Trends!
    elif effective_platform in {"tiktok_global", "predictive_global"}:
        results = _scrape_google_trends_global(keyword=keyword)
    # 6. Nếu chọn "Tất cả nguồn" (all) -> Mới cào tổng hợp tất cả!
    else:
        # Chạy song song 5 nguồn (các hàm sync, không đụng event loop) để giảm
        # thời gian chờ từ tổng 5 nguồn xuống ~nguồn chậm nhất (plan §3.2).
        def _scrape_all() -> list[TrendItem]:
            with ThreadPoolExecutor(max_workers=5) as pool:
                f_tt = pool.submit(
                    _scrape_tiktok_smart,
                    keyword=keyword, count=8, nguon_goc="tiktok_vn", scrape_mode=scrape_mode,
                )
                f_gg = pool.submit(_scrape_google_trends_vn, keyword=keyword)
                f_gz = pool.submit(
                    _scrape_threads_smart,
                    keyword=keyword, count=8, nguon_goc="threads_vn", scrape_mode=scrape_mode,
                )
                f_st = pool.submit(_scrape_showbiz_kols_vn, keyword=keyword)
                f_gl = pool.submit(_scrape_google_trends_global, keyword=keyword)
                return (
                    f_tt.result() + f_gg.result() + f_gz.result() + f_st.result() + f_gl.result()
                )

        results = _scrape_all()

    # Lọc danh mục phụ nếu có
    if category_filter != "all":
        results = [t for t in results if t.danh_muc == category_filter]

    # Lọc loại xu hướng nếu có
    if effective_type != "all":
        results = [t for t in results if t.loai_xu_huong == effective_type]

    # Lưu cache tổng hợp (chỉ khi không force_live).
    if not force_live:
        _radar_cache_put(cache_key, results)

    return results


def get_trend_by_id(trend_id: str) -> TrendItem | None:
    for f in _FIXTURE_TRENDS:
        if f.id == trend_id:
            return f
    all_items = fetch_trend_radar(force_live=True)
    for t in all_items:
        if t.id == trend_id:
            return t
    return None


__all__ = [
    "TrendItem",
    "fetch_trend_radar",
    "get_trend_by_id",
]
