# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Kiểm thử cho delivery_camoufox_source: parser giá, trích xuất dữ liệu, cache."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from ca_agents.clients.camoufox_client import CamoufoxUnavailable
from ca_agents.sources.delivery_camoufox_source import (
    _cache_get,
    _cache_key,
    _cache_put,
    _reset_cache,
    extract_delivery_stores_from_json,
    parse_price,
    scrape_delivery_stores_camoufox,
)
from ca_contracts.catchment_survey import StoreCandidate

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "delivery_stores_sample.json"


def test_parse_price_various_formats() -> None:
    assert parse_price("32.000đ") == 32000
    assert parse_price("35k") == 35000
    assert parse_price("29.5k") == 29500
    assert parse_price(45000) == 45000
    assert parse_price("45,000") == 45000
    assert parse_price("55k") == 55000
    assert parse_price("0") == 0
    assert parse_price("") == 0
    assert parse_price(None) == 0


def test_extract_delivery_stores_from_fixture() -> None:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    stores = extract_delivery_stores_from_json(raw)

    assert len(stores) == 6
    s1 = stores[0]
    assert s1.id == "res_001"
    assert "Chú Long" in s1.name
    assert s1.rating == 4.8
    assert s1.review_count == 2150
    assert s1.is_favorite is True
    assert len(s1.dishes) == 3

    best_seller = next(d for d in s1.dishes if d.is_bestseller)
    assert best_seller.price == 32000
    assert "đặc biệt" in best_seller.name.lower()


def test_delivery_cache_lifecycle() -> None:
    _reset_cache()
    key = _cache_key(10.78, 106.69, "cà phê", 5.0)

    assert _cache_get(key) is None

    sample_stores = [
        StoreCandidate(
            id="s1",
            name="Test",
            distance_km=1.0,
            rating=4.5,
            review_count=100,
        )
    ]
    _cache_put(key, sample_stores)

    hit = _cache_get(key)
    assert hit is not None
    assert len(hit) == 1
    assert hit[0].id == "s1"

    _reset_cache()
    assert _cache_get(key) is None


def test_scrape_delivery_stores_camoufox_unavailable() -> None:
    _reset_cache()
    with patch(
        "ca_agents.sources.delivery_camoufox_source.scrape_page",
        side_effect=CamoufoxUnavailable("Chưa cài đặt"),
    ):
        with pytest.raises(CamoufoxUnavailable):
            scrape_delivery_stores_camoufox(10.78, 106.69, "cà phê", 5.0)


# ── Dữ liệu lấy từ probe THẬT (2026-09-22) — chống hồi quy 2 bug đã gặp ──────


def test_city_slug_chon_dung_thanh_pho() -> None:
    """Slug khu vực phải suy từ tọa độ — URL listing không có slug sẽ 404/landing."""
    from ca_agents.sources.delivery_camoufox_source import _city_slug

    assert _city_slug(10.7769, 106.7009) == "ho-chi-minh"
    assert _city_slug(21.0285, 105.8542) == "ha-noi"
    assert _city_slug(16.0544, 108.2022) == "da-nang"
    # Tọa độ lạ (ngoài bảng) rơi về TP.HCM — không raise, không trả chuỗi rỗng.
    assert _city_slug(45.0, 90.0) == "ho-chi-minh"


def test_extract_ten_quan_tu_brand_name() -> None:
    """Payload thật từ `get_infos` chứa tên trong `brand.name`, không phải `name`.

    Bug cũ: parser chỉ đọc `name` top-level → 100% quán thật bị bỏ qua (mọi
    trường name rỗng), dù API trả dữ liệu đầy đủ. Test này khoá hành vi đúng.
    """
    payload = {
        "reply": {
            "delivery_infos": [
                {
                    "id": 118229,
                    "restaurant_id": 1027696,
                    "brand": {"name": "Đại Lợi - Bánh Mì Da Beo"},
                    "address": "115C Trần Quốc Thảo, P. 7, Quận 3",
                    "rating": {"avg": 5.0, "total_review": 10},
                    "is_quality_merchant": False,
                    "location_url": "ho-chi-minh",
                    "url_rewrite_name": "dai-loi-banh-mi-da-beo",
                },
                {
                    # Quán không có brand.name -> dùng `name` top-level (fixture cũ)
                    "restaurant_id": 999,
                    "name": "Quán Không Brand",
                    "rating": 4.2,
                },
            ]
        }
    }
    stores = extract_delivery_stores_from_json(payload)

    assert len(stores) == 2
    s1 = stores[0]
    assert s1.name == "Đại Lợi - Bánh Mì Da Beo"
    assert s1.rating == 5.0
    assert s1.review_count == 10
    assert s1.url == "https://shopeefood.vn/ho-chi-minh/dai-loi-banh-mi-da-beo"
    # Quán #2 vẫn đọc được tên từ `name` (tương thích fixture cũ).
    assert stores[1].name == "Quán Không Brand"


def test_fetch_shopeefood_page_gop_nhieu_lo_va_khu_trung() -> None:
    """`get_infos` trả 25 quán/lô — hàm phải gộp MỌI lô và khử trùng theo id.

    Bug cũ: chỉ lấy payload đầu tiên → 25/188 quán. Test mô phỏng SPA bắn 3 lô
    (có 1 id trùng lặp) và kiểm tra hàm gộp đủ 5 quán duy nhất.
    """
    from ca_agents.sources.delivery_camoufox_source import fetch_shopeefood_page

    logged: list[str] = []

    class _FakeResponse:
        def __init__(self, data: dict) -> None:
            self._data = data

        def json(self) -> dict:
            return self._data

    class _FakeLocator:
        def first(self) -> _FakeLocator:
            return self

        def click(self, timeout: int = 0) -> None:
            raise RuntimeError("trang không có nút phân trang")

    class _FakeContext:
        def set_geolocation(self, coords: dict) -> None:
            logged.append(f"geo:{coords['latitude']}")

    class _FakePage:
        """Page giả: goto() sẽ bắn 3 lô get_infos như SPA thật."""

        context = _FakeContext()

        def __init__(self) -> None:
            self._listeners: list = []
            self.url = ""

        def on(self, event: str, cb) -> None:
            self._listeners.append(cb)

        def remove_listener(self, event: str, cb) -> None:
            pass

        def goto(self, url: str, **kwargs) -> None:
            self.url = url
            logged.append(f"goto:{url}")
            # Lô 1: 2 quán; lô 2: 2 quán (1 trùng id); lô 3: 1 quán
            self._emit({"reply": {"search_result": [{"restaurant_ids": [1, 2, 3, 4, 5]}]}})
            self._emit({"reply": {"delivery_infos": [{"id": 1}, {"id": 2}]}})
            self._emit({"reply": {"delivery_infos": [{"id": 2}, {"id": 3}]}})
            self._emit({"reply": {"delivery_infos": [{"id": 4}]}})

        def _emit(self, data: dict) -> None:
            for cb in self._listeners:
                cb(_FakeResponse(data))

        def mouse(self):
            raise RuntimeError("hết trang")

        def locator(self, sel: str) -> _FakeLocator:
            return _FakeLocator()

    page = _FakePage()
    result = fetch_shopeefood_page(page, keyword="pho", lat=10.7769, lng=106.7009)

    infos = result["reply"]["delivery_infos"]
    assert len(infos) == 4, "phải gộp 4 quán duy nhất (id 2 trùng ở 2 lô)"
    assert [i["id"] for i in infos] == [1, 2, 3, 4]
    # URL phải là LISTING khu vực + ?q= (không phải /search?keyword=).
    assert "/ho-chi-minh/danh-sach-dia-diem-giao-tan-noi?q=pho" in logged[0] or any(
        "danh-sach-dia-diem" in entry for entry in logged
    )


def test_fetch_shopeefood_page_khong_co_du_lieu_tra_dict_rong() -> None:
    """Bị chặn/không có response → trả {} (fail-closed), không bịa dữ liệu (ADR-008)."""
    from ca_agents.sources.delivery_camoufox_source import fetch_shopeefood_page

    class _FakeContext:
        def set_geolocation(self, coords: dict) -> None:
            pass

    class _FakePage:
        context = _FakeContext()

        def on(self, event: str, cb) -> None:
            pass

        def remove_listener(self, event: str, cb) -> None:
            pass

        def goto(self, url: str, **kwargs) -> None:
            pass

    assert fetch_shopeefood_page(_FakePage(), "pho", 10.7769, 106.7009) == {}


def test_fetch_delivery_dishes_captures_payload() -> None:
    """fetch_delivery_dishes bắt đúng payload get_delivery_dishes từ listener."""
    from ca_agents.sources.delivery_camoufox_source import fetch_delivery_dishes

    class _FakeResponse:
        def __init__(self, url: str, data: dict) -> None:
            self.url = url
            self._data = data

        def json(self) -> dict:
            return self._data

    class _FakePage:
        url = "https://shopeefood.vn/quan-test"

        def __init__(self) -> None:
            self._listeners: list = []

        def on(self, event: str, cb) -> None:
            self._listeners.append(cb)
            # Giả lập response bắn về ngay sau khi gắn listener
            cb(
                _FakeResponse(
                    "https://gofood.vn/api/dish/get_delivery_dishes?id=123",
                    {
                        "reply": {
                            "menu_infos": [
                                {
                                    "dish_type_name": "Cơm",
                                    "dishes": [
                                        {"name": "Cơm sườn", "price": {"value": 35000}}
                                    ],
                                }
                            ]
                        }
                    },
                )
            )

        def remove_listener(self, event: str, cb) -> None:
            pass

        def goto(self, url: str, **kwargs) -> None:
            pass

    res = fetch_delivery_dishes(_FakePage(), "https://shopeefood.vn/quan-test", 10.77, 106.69)
    assert "reply" in res
    assert len(res["reply"]["menu_infos"]) == 1


def test_scrape_delivery_stores_respects_deadline() -> None:
    """Khi deadline đã cạn, scrape_delivery_stores không gọi cào menu cho các quán tiếp theo."""
    _reset_cache()
    from ca_agents.sources.delivery_camoufox_source import scrape_delivery_stores_camoufox

    fake_stores_payload = {
        "reply": {
            "delivery_infos": [
                {"id": 1, "restaurant_id": 1, "name": "Quán 1", "rating": 4.5, "url_rewrite_name": "q1", "location_url": "hcm"},
                {"id": 2, "restaurant_id": 2, "name": "Quán 2", "rating": 4.5, "url_rewrite_name": "q2", "location_url": "hcm"},
            ]
        }
    }

    menu_scraped = []

    with patch("ca_agents.sources.delivery_camoufox_source.scrape_page", return_value=fake_stores_payload):
        with patch("ca_agents.sources.delivery_camoufox_source.scrape_delivery_menu_camoufox", side_effect=lambda *a, **kw: menu_scraped.append(a)):
            # Với deadline 0, vòng lặp menu phải dừng ngay lập tức
            stores = scrape_delivery_stores_camoufox(10.78, 106.69, "cơm", 5.0, deadline_s=0.0)
            assert len(stores) == 2
            assert len(menu_scraped) == 0, "Không được cào menu khi deadline_s <= 10s"

