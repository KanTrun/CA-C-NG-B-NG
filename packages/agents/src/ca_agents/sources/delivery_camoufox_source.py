"""Cào dữ liệu quán và menu đối thủ F&B bằng Camoufox (ShopeeFood / Delivery).

Tuân thủ thiết kế:
- fetch_delivery_page(page, ...): Điều hướng trình duyệt, bắt JSON API nội bộ.
- extract_delivery_stores_from_json(data): Hàm THUẦN, test bằng fixture offline.
- extract_delivery_stores_from_html(html): Parser HTML dự phòng.
- scrape_delivery_stores_camoufox(...): Orchestrate qua camoufox_client.scrape_page + cache TTL.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any
from urllib.parse import quote

from ca_contracts.catchment_survey import DishItem, StoreCandidate

from ca_agents.clients.camoufox_client import CamoufoxUnavailable, scrape_page

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_TTL_S = 1800  # 30 phút cache cho kết quả khảo sát thị trường
_cache: dict[str, tuple[float, list[StoreCandidate]]] = {}

# Tọa độ trung tâm các thành phố ShopeeFood phục vụ — dùng để suy slug khu vực
# trong PATH URL (ShopeeFood không nhận khu vực qua query string). Mở rộng khi
# cần thêm thành phố: thêm (lat, lng, slug) vào cuối.
_CITY_COORDS: tuple[tuple[float, float, str], ...] = (
    (10.7769, 106.7009, "ho-chi-minh"),
    (21.0285, 105.8542, "ha-noi"),
    (16.0544, 108.2022, "da-nang"),
    (10.0452, 105.7469, "can-tho"),
    (20.8449, 106.6881, "hai-phong"),
    (12.2388, 109.1967, "nha-trang"),
    (11.9404, 108.4583, "da-lat"),
    (10.9804, 106.6519, "binh-duong"),
    (10.9447, 106.8243, "bien-hoa"),
)

# Ngưỡng "còn trong vùng phục vụ": bình phương khoảng cách độ (≈ 150 km). Tọa độ
# xa hơn (nước ngoài, giữa biển...) không được gán bừa cho thành phố gần nhất,
# mà rơi về TP.HCM — thị trường chính, cũng là mặc định của mọi tài liệu dự án.
_CITY_FALLBACK_MAX_DEG2 = 2.0
_CITY_FALLBACK_SLUG = "ho-chi-minh"

_PRICE_RE = re.compile(r"([\d.,]+)\s*(?:đ|k|vnd)?", re.IGNORECASE)


def parse_price(val: Any) -> int:
    """Chuyển đổi giá tiền từ mọi định dạng (int, "35.000đ", "35k", "35,000") về int VNĐ."""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip().lower()
    if not s:
        return 0

    # Trường hợp viết tắt 35k -> 35000
    if s.endswith("k"):
        num_str = s[:-1].strip().replace(",", ".")
        try:
            return int(float(num_str) * 1000)
        except ValueError:
            pass

    # Trường hợp định dạng tiền tệ "35.000đ" hoặc "35,000"
    m = _PRICE_RE.search(s)
    if not m:
        return 0

    clean_num = m.group(1).replace(".", "").replace(",", "")
    try:
        return int(clean_num)
    except ValueError:
        return 0


def _get_cache_ttl_s() -> int:
    try:
        return max(60, int(os.getenv("CA_DELIVERY_CACHE_TTL_S", str(_DEFAULT_CACHE_TTL_S))))
    except ValueError:
        return _DEFAULT_CACHE_TTL_S


def _cache_key(lat: float, lng: float, keyword: str, radius_km: float) -> str:
    return f"delivery:{round(lat, 3)}:{round(lng, 3)}:{(keyword or '').strip().lower()}:{round(radius_km, 1)}"


def _cache_get(key: str) -> list[StoreCandidate] | None:
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is None:
        return None
    cached_at, items = hit
    if now - cached_at > _get_cache_ttl_s():
        _cache.pop(key, None)
        return None
    return items


def _cache_put(key: str, items: list[StoreCandidate]) -> None:
    _cache[key] = (time.monotonic(), items)


def _reset_cache() -> None:
    """Xóa cache bộ nhớ (dùng cho test)."""
    _cache.clear()


def extract_delivery_stores_from_json(payload: dict[str, Any]) -> list[StoreCandidate]:
    """Trích xuất danh sách quán và menu từ payload JSON của ShopeeFood/Delivery API.

    Hàm thuần (pure function) — dễ dàng kiểm thử bằng JSON fixture tĩnh.
    """
    stores: list[StoreCandidate] = []
    if not isinstance(payload, dict):
        return stores

    # Xử lý các cấu trúc payload phổ biến của ShopeeFood / Foody
    raw_restaurants = (
        payload.get("restaurants")
        or payload.get("reply", {}).get("restaurants")
        or payload.get("data", {}).get("restaurants")
        or payload.get("items")
        or payload.get("reply", {}).get("delivery_infos")
        or []
    )

    for item in raw_restaurants:
        if not isinstance(item, dict):
            continue

        store_id = str(item.get("id") or item.get("restaurant_id") or "")
        # Payload THẬT từ `get_infos` (2026) đặt tên quán trong `brand.name`
        # (không phải top-level `name`); fixture cũ dùng `name` trực tiếp.
        brand_raw = item.get("brand")
        brand_name = brand_raw.get("name") if isinstance(brand_raw, dict) else None
        name = str(item.get("name") or item.get("restaurant_name") or brand_name or "").strip()
        if not name:
            continue

        address = str(item.get("address") or item.get("short_address") or "").strip()
        url = str(item.get("url") or item.get("share_url") or "")
        # Endpoint mới (2026): `delivery_infos` không có `url` đầy đủ, chỉ có
        # `url_rewrite_name` + `location_url` → xây URL trang quán để lấy menu.
        if not url:
            loc = str(item.get("location_url") or "").strip()
            slug = str(item.get("url_rewrite_name") or item.get("restaurant_url") or "").strip()
            if loc and slug:
                url = f"https://shopeefood.vn/{loc}/{slug}"

        # Rating: thang 5.0 — endpoint mới bọc trong `rating.avg`
        rating_raw = (
            item.get("rating")
            or item.get("avg_rating")
            or item.get("star")
            or 0.0
        )
        if isinstance(rating_raw, dict):
            rating_raw = rating_raw.get("avg") or 0.0
        try:
            rating = round(float(rating_raw), 1)
        except (ValueError, TypeError):
            rating = 0.0

        # Review count / Total reviews — endpoint mới bọc trong `rating.total_review`
        review_count_raw = (
            item.get("review_count")
            or item.get("rating_count")
            or item.get("total_rating")
            or item.get("total_reviews")
            or 0
        )
        if isinstance(item.get("rating"), dict):
            review_count_raw = (
                item["rating"].get("total_review")
                or item["rating"].get("total_reviews")
                or review_count_raw
            )
        try:
            review_count = int(review_count_raw)
        except (ValueError, TypeError):
            review_count = 0

        # Huy hiệu Quán yêu thích / Đối tác
        is_favorite = bool(
            item.get("is_favorite")
            or item.get("is_quality_merchant")
            or item.get("is_official")
            or "quán yêu thích" in str(item.get("badges", "")).lower()
        )

        # Distance km
        dist_raw = item.get("distance_km") or item.get("distance") or 0.0
        try:
            distance_km = round(float(dist_raw), 2)
        except (ValueError, TypeError):
            distance_km = 0.0

        sold_text = str(item.get("sold_count_text") or item.get("total_order") or "")

        # Trích xuất danh sách món
        dishes: list[DishItem] = []
        raw_dishes = (
            item.get("dishes")
            or item.get("menu_items")
            or item.get("catalogues")
            or []
        )

        for d in raw_dishes:
            if not isinstance(d, dict):
                continue
            dish_name = str(d.get("name") or d.get("dish_name") or "").strip()
            dish_price = parse_price(d.get("price") or d.get("price_vnd") or 0)
            if not dish_name or dish_price <= 0:
                continue

            is_bestseller = bool(
                d.get("is_bestseller")
                or d.get("is_best_seller")
                or d.get("is_signature")
                or "bán chạy" in dish_name.lower()
                or "hot" in dish_name.lower()
            )
            cat = str(d.get("category") or d.get("category_name") or "")

            dishes.append(
                DishItem(
                    name=dish_name,
                    price=dish_price,
                    is_bestseller=is_bestseller,
                    category=cat,
                )
            )

        stores.append(
            StoreCandidate(
                id=store_id,
                name=name,
                address=address,
                distance_km=distance_km,
                rating=rating,
                review_count=review_count,
                is_favorite=is_favorite,
                sold_count_text=sold_text,
                url=url,
                dishes=dishes,
            )
        )

    return stores


def _city_slug(lat: float, lng: float) -> str:
    """Suy slug thành phố ShopeeFood từ tọa độ (chọn thành phố gần nhất).

    ShopeeFood nhận diện khu vực qua slug trong PATH (`/ho-chi-minh/...`), không
    nhận qua query string — nên URL listing bắt buộc phải có slug. Bảng tọa độ
    dưới đây phủ các thành phố lớn; tọa độ lạ (xa hơn `_CITY_FALLBACK_MAX_DEG2`)
    rơi về TP.HCM (thị trường chính, cũng là mặc định trong mọi tài liệu dự án).
    """
    best_slug = _CITY_FALLBACK_SLUG
    best_dist = float("inf")
    for clat, clng, slug in _CITY_COORDS:
        d = (lat - clat) ** 2 + (lng - clng) ** 2
        if d < best_dist:
            best_dist = d
            best_slug = slug
    # Ngoài vùng phục vụ → không gán bừa thành phố gần nhất.
    if best_dist > _CITY_FALLBACK_MAX_DEG2:
        return _CITY_FALLBACK_SLUG
    return best_slug


class _ShopeeListingCollector:
    """Thu thập responses từ ShopeeFood listing page qua event listener Playwright."""

    def __init__(self, lat: float, lng: float, keyword: str) -> None:
        self.lat = lat
        self.lng = lng
        self.keyword = keyword
        self.merged: list[dict[str, Any]] = []
        self.seen_ids: set[Any] = set()
        self.total_ids: int = 0

    def on_response(self, response: Any) -> None:
        try:
            data = response.json()
        except Exception:
            return
        if not isinstance(data, dict):
            return
        reply = data.get("reply")
        if not isinstance(reply, dict):
            return

        # search_global: tổng số id khớp keyword (chỉ để log/đối chiếu)
        search_result = reply.get("search_result")
        if isinstance(search_result, list):
            for item in search_result:
                if isinstance(item, dict) and item.get("restaurant_ids"):
                    self.total_ids = len(item["restaurant_ids"])

        # get_infos / get_browsing_infos: chi tiết từng quán (nhiều lô)
        infos = reply.get("delivery_infos")
        if isinstance(infos, list):
            for info in infos:
                if not isinstance(info, dict):
                    continue
                rid = info.get("restaurant_id") or info.get("id")
                rid_text = str(rid) if rid is not None else ""
                key: Any = int(rid_text) if rid_text.isdigit() else rid_text
                if key in self.seen_ids:
                    continue
                self.seen_ids.add(key)
                self.merged.append(info)

    def setup(self, page: Any) -> None:
        """Gắn listener VÀ set geolocation TRƯỚC KHI page.goto()."""
        if hasattr(page, "on"):
            page.on("response", self.on_response)
        if hasattr(page, "context") and hasattr(page.context, "set_geolocation"):
            try:
                page.context.set_geolocation({"latitude": self.lat, "longitude": self.lng})
            except Exception:
                pass


class _ShopeeMenuCollector:
    """Thu thập menu quán ShopeeFood (`get_delivery_dishes`) qua event listener."""

    def __init__(self, lat: float, lng: float) -> None:
        self.lat = lat
        self.lng = lng
        self.captured_payloads: list[dict[str, Any]] = []

    def on_response(self, response: Any) -> None:
        url = getattr(response, "url", "") or ""
        # Endpoint menu thực tế (2026): `api/dish/get_delivery_dishes` (không phải
        # `api/delivery/get_delivery_dishes`).
        if "get_delivery_dishes" in url:
            try:
                data = response.json()
                if isinstance(data, dict):
                    self.captured_payloads.append(data)
            except Exception:
                pass

    def setup(self, page: Any) -> None:
        """Gắn listener VÀ set geolocation TRƯỚC KHI page.goto()."""
        if hasattr(page, "on"):
            page.on("response", self.on_response)
        if hasattr(page, "context") and hasattr(page.context, "set_geolocation"):
            try:
                page.context.set_geolocation({"latitude": self.lat, "longitude": self.lng})
            except Exception:
                pass


def fetch_shopeefood_page(
    page: Any,
    keyword: str,
    lat: float,
    lng: float,
    radius_km: float = 5.0,
    max_scrolls: int = 8,
    collector: _ShopeeListingCollector | None = None,
) -> dict[str, Any]:
    """Điều hướng trang LISTING ShopeeFood và bắt danh sách quán theo keyword.

    Endpoint thật (xác minh 2026-09-22 bằng `scripts/probe_sf_kw_endpoint.py`):

    1. URL đúng: `https://shopeefood.vn/{slug}/danh-sach-dia-diem-giao-tan-noi?q=<kw>`.
       `/search?keyword=` chỉ là landing — trả danh sách CHUNG của thành phố,
       KHÔNG theo keyword (bug cũ: 9 quán bất kỳ cho mọi từ khóa).
    2. SPA gọi `POST /api/delivery/search_global` {keyword, city_id, sort_type}
       → `reply.search_result[].restaurant_ids` (toàn bộ id khớp keyword).
    3. Rồi gọi `POST /api/delivery/get_infos` {restaurant_ids: [25 id/lô]}
       → `reply.delivery_infos` (chi tiết quán). Cuộn + bấm nút phân trang để
       SPA tải các lô tiếp theo.

    Hàm gộp MỌI lô `delivery_infos` bắt được (khử trùng theo restaurant_id) và
    trả `{"reply": {"delivery_infos": [...]}}` — giữ nguyên shape để
    `extract_delivery_stores_from_json` dùng lại không cần sửa.

    Gọi API trực tiếp (httpx / page.request / fetch) đều bị chặn: 403 hoặc CORS.
    Cách duy nhất ổn định là để SPA tự gọi rồi bắt response — như hàm này.
    """
    if collector is None:
        collector = _ShopeeListingCollector(lat, lng, keyword)
        collector.setup(page)

    slug = _city_slug(lat, lng)
    listing_url = (
        f"https://shopeefood.vn/{slug}/danh-sach-dia-diem-giao-tan-noi"
        f"?q={quote(keyword)}"
    )

    try:
        current_url = getattr(page, "url", "") or ""
        if "danh-sach-dia-diem" not in current_url:
            page.goto(listing_url, timeout=15000)
        time.sleep(1.0)  # lô get_infos đầu tiên

        # Tải thêm quán: cuộn đáy + bấm nút phân trang now.vn. Dừng khi 3 vòng
        # liên tiếp không thêm quán mới (hết kết quả hoặc bị chặn).
        stable = 0
        for _ in range(max(1, max_scrolls)):
            before = len(collector.merged)
            try:
                page.mouse.wheel(0, 5000)
            except Exception:
                pass
            time.sleep(0.5)
            try:
                page.locator(
                    "a .icon-paging-next, .icon-paging-next"
                ).first.click(timeout=500)
                time.sleep(0.6)
            except Exception:
                pass  # trang không có nút phân trang: chỉ cuộn là đủ
            stable = stable + 1 if len(collector.merged) == before else 0
            if stable >= 3:
                break
    except Exception as exc:
        logger.warning("Lỗi trong quá trình fetch_shopeefood_page: %s", exc)
    finally:
        try:
            page.remove_listener("response", collector.on_response)
        except Exception:
            pass

    logger.info(
        "shopeefood_listing slug=%s keyword=%s ids_search_global=%d quan_bat_duoc=%d",
        slug,
        keyword,
        collector.total_ids,
        len(collector.merged),
    )
    if collector.merged:
        return {"reply": {"delivery_infos": collector.merged}}
    return {}


def fetch_delivery_dishes(
    page: Any,
    store_url: str,
    lat: float,
    lng: float,
    collector: _ShopeeMenuCollector | None = None,
) -> dict[str, Any]:
    """Điều hướng trang quán ShopeeFood và bắt menu (`get_delivery_dishes`).

    ShopeeFood (2026) trả menu qua endpoint `get_delivery_dishes` khi vào trang
    quán. Hàm bắt payload chứa `reply.menu_infos` (danh sách món theo nhóm).
    """
    if collector is None:
        collector = _ShopeeMenuCollector(lat, lng)
        collector.setup(page)

    try:
        current_url = getattr(page, "url", "") or ""
        if not current_url or store_url not in current_url:
            page.goto(store_url, timeout=10000)
        # Chờ tối đa 3 giây cho SPA nạp menu qua API get_delivery_dishes nếu chưa có
        for _ in range(6):
            if collector.captured_payloads:
                break
            time.sleep(0.5)
    except Exception as exc:
        logger.warning("Lỗi trong quá trình fetch_delivery_dishes: %s", exc)
    finally:
        try:
            page.remove_listener("response", collector.on_response)
        except Exception:
            pass

    if collector.captured_payloads:
        return collector.captured_payloads[0]
    return {}


def extract_delivery_dishes_from_json(payload: dict[str, Any]) -> list[DishItem]:
    """Trích xuất danh sách món từ payload `get_delivery_dishes`.

    Cấu trúc (2026): `reply.menu_infos[]` mỗi nhóm có `dish_type_name` và
    `dishes[]`; mỗi món có `name` và `price.value` (VNĐ).
    """
    dishes: list[DishItem] = []
    if not isinstance(payload, dict):
        return dishes

    menu_infos = payload.get("reply", {}).get("menu_infos", [])
    for group in menu_infos:
        if not isinstance(group, dict):
            continue
        category = str(group.get("dish_type_name") or "")
        for d in group.get("dishes", []):
            if not isinstance(d, dict):
                continue
            dish_name = str(d.get("name") or "").strip()
            if not dish_name:
                continue
            price_raw = d.get("price")
            if isinstance(price_raw, dict):
                price_raw = price_raw.get("value") or price_raw.get("text") or 0
            dish_price = parse_price(price_raw)
            if dish_price <= 0:
                continue
            dishes.append(
                DishItem(
                    name=dish_name,
                    price=dish_price,
                    is_bestseller=False,
                    category=category,
                )
            )
    return dishes


def scrape_delivery_stores_camoufox(
    latitude: float,
    longitude: float,
    keyword: str,
    radius_km: float = 5.0,
    deadline_s: float | None = None,
) -> list[StoreCandidate]:
    """Hàm điều phối cào danh sách quán qua Camoufox có cache.

    `deadline_s` là thời gian còn lại của job khảo sát: hết hạn thì dừng lấy menu
    để nhường thời gian cho các bước sau, thay vì treo tới khi worker bị restart.
    """
    cache_k = _cache_key(latitude, longitude, keyword, radius_km)
    cached = _cache_get(cache_k)
    if cached is not None:
        logger.info("Delivery Camoufox cache hit cho key=%s", cache_k)
        return cached

    collector = _ShopeeListingCollector(latitude, longitude, keyword)

    def _extractor(page: Any) -> dict[str, Any]:
        return fetch_shopeefood_page(
            page=page,
            keyword=keyword,
            lat=latitude,
            lng=longitude,
            radius_km=radius_km,
            collector=collector,
        )

    slug = _city_slug(latitude, longitude)
    target_url = (
        f"https://shopeefood.vn/{slug}/danh-sach-dia-diem-giao-tan-noi"
        f"?q={quote(keyword)}"
    )
    timeout_s = 20 if deadline_s is None else max(5, min(25, int(deadline_s)))
    try:
        result_json = scrape_page(
            target_url, _extractor, timeout_s=timeout_s, setup_page=collector.setup
        )
    except CamoufoxUnavailable:
        logger.info("Camoufox không khả dụng cho delivery scraping")
        raise
    except Exception as exc:
        logger.warning("Scrape delivery thất bại: %s", exc)
        return []

    stores = extract_delivery_stores_from_json(result_json)
    if stores:
        # Lấy menu cho từng quán (tối đa 3 quán đầu để đảm bảo ngân sách thời gian).
        # Bọc try/except: menu lỗi KHÔNG được làm mất danh sách quán.
        start_mono = time.monotonic()
        for store in stores[:3]:
            if deadline_s is not None:
                elapsed = time.monotonic() - start_mono
                con_lai = deadline_s - elapsed
                if con_lai <= 10.0:
                    logger.info("Ngân sách thời gian còn ít (%.1fs) — dừng cào menu", con_lai)
                    break
            if store.url:
                try:
                    menu = scrape_delivery_menu_camoufox(
                        store.url, latitude, longitude, deadline_s=10.0
                    )
                    if menu:
                        store.dishes = menu
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Lấy menu quán %s thất bại: %s", store.url[:80], exc)
        _cache_put(cache_k, stores)
    return stores


def scrape_delivery_menu_camoufox(
    store_url: str,
    latitude: float,
    longitude: float,
    deadline_s: float | None = None,
) -> list[DishItem]:
    """Cào menu của một quán ShopeeFood qua Camoufox (endpoint `get_delivery_dishes`)."""
    if not store_url:
        return []

    collector = _ShopeeMenuCollector(latitude, longitude)

    def _extractor(page: Any) -> dict[str, Any]:
        return fetch_delivery_dishes(
            page=page,
            store_url=store_url,
            lat=latitude,
            lng=longitude,
            collector=collector,
        )

    timeout_s = 10 if deadline_s is None else max(5, min(12, int(deadline_s)))
    try:
        result_json = scrape_page(
            store_url, _extractor, timeout_s=timeout_s, setup_page=collector.setup
        )
    except CamoufoxUnavailable:
        logger.info("Camoufox không khả dụng cho delivery menu scraping")
        return []
    except Exception as exc:
        logger.warning("Scrape delivery menu thất bại (%s): %s", store_url[:80], exc)
        return []

    return extract_delivery_dishes_from_json(result_json)