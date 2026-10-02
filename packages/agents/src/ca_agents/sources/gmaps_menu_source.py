"""Cào ảnh thực đơn (Menu) đối thủ F&B trên Google Maps bằng Camoufox.

Phase 2: 2-step photo fetch — menu tab trước, all_photos fallback nếu menu tab trống.
Fix hard-coded rating/review_count. Track photo_source per place.
SOURCE_BLOCKED handling: exponential backoff + jitter (max 3 retries).
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Any

from ca_contracts.catchment_survey import StoreCandidate
from ca_contracts.catchment_survey_v2 import SurveyErrorCode

from ca_agents.clients.camoufox_client import CamoufoxUnavailable, scrape_page
from ca_agents.sources.scraper_selectors import (
    DAU_HIEU_BI_CHAN,
    GMAPS_SEL_ANH_TRONG_VUNG,
    GMAPS_SEL_KHUNG_KET_QUA,
    GMAPS_SEL_NUT_TAT_CA_ANH,
    GMAPS_SEL_NUT_THUC_DON,
    GMAPS_SEL_RATING,
    GMAPS_SEL_SO_REVIEW,
    GMAPS_SEL_TEN_QUAN,
)

logger = logging.getLogger(__name__)

# Selector nằm ở `scraper_selectors.py` — canary test hàng ngày đọc CHÍNH danh sách
# này để dò trang thật. Nếu tách riêng ở đây thì canary phải chép lại và sẽ vẫn
# xanh sau khi Google đổi cấu trúc (plan mục 7). Import theo TÊN chứ không theo chỉ
# số tuple: đổi thứ tự khai báo không thể làm rating bị đọc nhầm thành số review.
_SEL_NUT_THUC_DON = GMAPS_SEL_NUT_THUC_DON
_SEL_NUT_TAT_CA_ANH = GMAPS_SEL_NUT_TAT_CA_ANH
_SEL_ANH_TRONG_VUNG = GMAPS_SEL_ANH_TRONG_VUNG
_SEL_KHUNG_KET_QUA = GMAPS_SEL_KHUNG_KET_QUA
_SEL_TEN_QUAN = GMAPS_SEL_TEN_QUAN
_SEL_RATING = GMAPS_SEL_RATING
_SEL_SO_REVIEW = GMAPS_SEL_SO_REVIEW

_DEFAULT_CACHE_TTL_S = 1800
_gmaps_cache: dict[str, tuple[float, list[StoreCandidate]]] = {}

# SOURCE_BLOCKED retry config
_MAX_BLOCK_RETRIES = 3
_BACKOFF_BASE_S = 2.0
_BACKOFF_MAX_S = 30.0


@dataclass
class SourceBlockStats:
    """Thống kê block rate per source — dùng log + alert."""

    total_requests: int = 0
    blocked_count: int = 0
    last_blocked_at: float = 0.0

    @property
    def block_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.blocked_count / self.total_requests


_source_stats: dict[str, SourceBlockStats] = {}


def _get_source_stats(source: str) -> SourceBlockStats:
    if source not in _source_stats:
        _source_stats[source] = SourceBlockStats()
    return _source_stats[source]


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff + jitter cho SOURCE_BLOCKED retry."""
    # `2 ** attempt` mypy suy ra Any (int ** int có thể tràn sang float), nên phải
    # float() tường minh: hàm này quyết định thời gian ngủ giữa các lần retry, trả
    # nhầm kiểu là backoff im lặng mất tác dụng.
    delay: float = min(_BACKOFF_BASE_S * float(2**attempt), _BACKOFF_MAX_S)
    jitter: float = random.uniform(0, delay * 0.3)
    return delay + jitter


def _cache_key(lat: float, lng: float, keyword: str, radius_km: float) -> str:
    return f"gmaps:{round(lat, 3)}:{round(lng, 3)}:{(keyword or '').strip().lower()}:{round(radius_km, 1)}"


def _cache_get(key: str) -> list[StoreCandidate] | None:
    now = time.monotonic()
    hit = _gmaps_cache.get(key)
    if hit is None:
        return None
    cached_at, items = hit
    if now - cached_at > _DEFAULT_CACHE_TTL_S:
        _gmaps_cache.pop(key, None)
        return None
    return items


def _cache_put(key: str, items: list[StoreCandidate]) -> None:
    _gmaps_cache[key] = (time.monotonic(), items)


def _reset_gmaps_cache() -> None:
    _gmaps_cache.clear()


def extract_gmaps_places_from_payload(payload: dict[str, Any]) -> list[StoreCandidate]:
    """Hàm THUẦN trích xuất danh sách quán và link ảnh menu từ dữ liệu Google Maps Place."""
    stores: list[StoreCandidate] = []
    if not isinstance(payload, dict):
        return stores

    raw_places = payload.get("places") or payload.get("results") or []
    for p in raw_places:
        if not isinstance(p, dict):
            continue

        store_id = str(p.get("id") or p.get("place_id") or "")
        name = str(p.get("name") or p.get("title") or "").strip()
        if not name:
            continue

        address = str(p.get("address") or p.get("vicinity") or "")
        rating = float(p.get("rating") or p.get("stars") or 0.0)
        review_count = int(p.get("review_count") or p.get("user_ratings_total") or 0)
        dist_km = float(p.get("distance_km") or 0.0)
        url = str(p.get("url") or "")

        # Trích xuất URL các ảnh trong album Menu
        menu_images = []
        raw_photos = p.get("menu_photos") or p.get("photos") or []
        for photo in raw_photos:
            if isinstance(photo, str) and photo.startswith("http"):
                menu_images.append(photo)
            elif isinstance(photo, dict) and "url" in photo:
                menu_images.append(str(photo["url"]))

        stores.append(
            StoreCandidate(
                id=store_id,
                name=name,
                address=address,
                distance_km=dist_km,
                rating=rating,
                review_count=review_count,
                url=url,
                menu_image_urls=menu_images,
                dishes=[],
            )
        )
    return stores


def _extract_rating_from_text(text: str) -> float:
    """Parse rating từ text như '4,5' hoặc '4.5'."""
    cleaned = text.strip().replace(",", ".")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _extract_review_count_from_text(text: str) -> int:
    """Parse review count từ text như '(1.250)' hoặc '1.250 bài đánh giá'."""
    import re
    digits = re.sub(r"[^0-9]", "", text)
    try:
        return int(digits) if digits else 0
    except (ValueError, TypeError):
        return 0


def _fetch_menu_tab_photos(page: Any, max_images: int) -> list[str]:
    """Step 1: Lấy ảnh từ tab Menu/Thực đơn."""
    menu_tab = page.locator(_SEL_NUT_THUC_DON).first
    if not menu_tab.is_visible():
        return []

    menu_tab.click()
    time.sleep(1.0)

    photo_urls: list[str] = []
    imgs = page.locator(_SEL_ANH_TRONG_VUNG).all()
    for img in imgs[:max_images]:
        src = img.get_attribute("src")
        if src and src.startswith("http"):
            photo_urls.append(src)
    return photo_urls


def _fetch_all_photos_filtered(page: Any, max_images: int) -> list[str]:
    """Step 2 fallback: Lấy ảnh từ All Photos, lọc ảnh có text/menu board."""
    all_photos_tab = page.locator(_SEL_NUT_TAT_CA_ANH).first
    if not all_photos_tab.is_visible():
        return []

    all_photos_tab.click()
    time.sleep(1.5)

    photo_urls: list[str] = []
    imgs = page.locator(_SEL_ANH_TRONG_VUNG).all()
    for img in imgs[:max_images * 2]:
        src = img.get_attribute("src")
        if src and src.startswith("http"):
            photo_urls.append(src)
        if len(photo_urls) >= max_images:
            break
    return photo_urls


def fetch_gmaps_menu_images_page(
    page: Any,
    keyword: str,
    lat: float,
    lng: float,
    radius_km: float = 3.0,
    max_images: int = 3,
) -> dict[str, Any]:
    """Điều hướng Google Maps tìm kiếm F&B và trích xuất ảnh menu (2-step).

    Step 1: Menu tab → ảnh menu trực tiếp (photo_source="menu_tab")
    Step 2: All Photos fallback → lọc ảnh có menu board (photo_source="all_photos_filtered")

    Fix: rating/review_count lấy từ page thật, không hard-code.
    """
    captured_places: list[dict[str, Any]] = []
    stats = _get_source_stats("gmaps")

    try:
        page.context.set_geolocation({"latitude": lat, "longitude": lng})
        search_query = f"{keyword} gần đây"
        search_url = f"https://www.google.com/maps/search/{search_query}/@{lat},{lng},15z"
        page.goto(search_url, wait_until="networkidle", timeout=30000)
        time.sleep(3.0)

        feed_items = page.locator(_SEL_KHUNG_KET_QUA).all()
        for idx, item in enumerate(feed_items[:10]):
            try:
                title = item.locator(_SEL_TEN_QUAN).inner_text()
                if not title:
                    continue

                # Lấy rating + review_count từ page thật
                rating_text = item.locator(_SEL_RATING).first.inner_text()
                rating = _extract_rating_from_text(rating_text)

                review_text = item.locator(_SEL_SO_REVIEW).first.inner_text()
                review_count = _extract_review_count_from_text(review_text)

                item.click()
                time.sleep(1.5)

                # 2-step photo fetch
                photo_urls = _fetch_menu_tab_photos(page, max_images)
                photo_source = "menu_tab" if photo_urls else ""

                if not photo_urls:
                    photo_urls = _fetch_all_photos_filtered(page, max_images)
                    photo_source = "all_photos_filtered" if photo_urls else ""

                captured_places.append({
                    "id": f"gmap_{idx}",
                    "name": title,
                    "rating": rating,
                    "review_count": review_count,
                    "menu_photos": photo_urls,
                    "photo_source": photo_source,
                })
                stats.total_requests += 1

            except Exception:
                continue

    except Exception as exc:
        err_msg = str(exc).lower()
        stats.total_requests += 1

        # Detect SOURCE_BLOCKED
        if any(kw in err_msg for kw in DAU_HIEU_BI_CHAN):
            stats.blocked_count += 1
            stats.last_blocked_at = time.time()
            logger.warning(
                "SOURCE_BLOCKED: gmaps (block_rate=%.1f%%): %s",
                stats.block_rate * 100, exc,
            )
            return {
                "places": [],
                "error_code": SurveyErrorCode.SOURCE_BLOCKED,
                "error_detail": str(exc),
            }

        logger.warning("Lỗi fetch_gmaps_menu_images_page: %s", exc)

    return {"places": captured_places}


def scrape_gmaps_menu_images_camoufox(
    latitude: float,
    longitude: float,
    keyword: str,
    radius_km: float = 3.0,
    max_images: int = 3,
    deadline_s: float | None = None,
) -> list[StoreCandidate]:
    """Điều phối cào ảnh menu Google Maps bằng Camoufox có cache + SOURCE_BLOCKED retry.

    `deadline_s` là thời gian còn lại của job khảo sát: không retry khi đã cạn
    ngân sách (mỗi lần retry là một lượt proxy tính tiền thật).
    """
    cache_k = _cache_key(latitude, longitude, keyword, radius_km)
    cached = _cache_get(cache_k)
    if cached is not None:
        return cached

    target_url = f"https://www.google.com/maps/search/{keyword}/@{latitude},{longitude},15z"
    last_result: dict[str, Any] = {"places": []}

    for attempt in range(_MAX_BLOCK_RETRIES + 1):
        def _extractor(page: Any) -> dict[str, Any]:
            return fetch_gmaps_menu_images_page(
                page=page,
                keyword=keyword,
                lat=latitude,
                lng=longitude,
                radius_km=radius_km,
                max_images=max_images,
            )

        timeout_s = None if deadline_s is None else max(5, int(deadline_s))
        try:
            result_json = scrape_page(target_url, _extractor, timeout_s=timeout_s)
        except CamoufoxUnavailable:
            logger.info("Camoufox không khả dụng cho Google Maps menu scraping")
            raise
        except Exception as exc:
            logger.warning("Scrape Google Maps thất bại: %s", exc)
            return []

        # Check SOURCE_BLOCKED
        if result_json.get("error_code") == SurveyErrorCode.SOURCE_BLOCKED:
            if attempt < _MAX_BLOCK_RETRIES and (deadline_s is None or deadline_s > 0):
                delay = _backoff_delay(attempt)
                logger.info(
                    "SOURCE_BLOCKED retry %d/%d, waiting %.1fs",
                    attempt + 1, _MAX_BLOCK_RETRIES, delay,
                )
                time.sleep(delay)
                continue
            logger.warning(
                "SOURCE_BLOCKED: gmaps exhausted %d retries", _MAX_BLOCK_RETRIES
            )
            return []

        last_result = result_json
        break

    stores = extract_gmaps_places_from_payload(last_result)
    if stores:
        _cache_put(cache_k, stores)
    return stores


def get_source_block_stats() -> dict[str, SourceBlockStats]:
    """Trả về thống kê block rate per source — dùng cho monitoring."""
    return dict(_source_stats)
