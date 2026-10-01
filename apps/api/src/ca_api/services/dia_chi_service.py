"""Dịch vụ tra cứu danh mục địa chính Việt Nam (Tỉnh/Thành phố, Quận/Huyện, Phường/Xã).

Hỗ trợ chuẩn hóa địa chỉ cho thông tin quán (/cau-hinh-quan) và tính toán thời tiết,
giao hàng, hiển thị bản đồ.
- Tự động cache bộ nhớ để phản hồi tức thì (< 5ms).
- Tích hợp fallback offline từ file dữ liệu có sẵn khi mất mạng hoặc API chậm.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, cast

log = logging.getLogger(__name__)

_DIR = Path(__file__).resolve().parent
_PROVINCES_FALLBACK_FILE = _DIR / "vietnam_provinces.json"
_DISTRICTS_FALLBACK_FILE = _DIR / "vietnam_districts_fallback.json"

# In-memory caches
_PROVINCES_CACHE: list[dict[str, Any]] | None = None
_DISTRICTS_CACHE: dict[int, list[dict[str, Any]]] = {}
_WARDS_CACHE: dict[int, list[dict[str, Any]]] = {}


def _load_provinces_fallback() -> list[dict[str, Any]]:
    if _PROVINCES_FALLBACK_FILE.exists():
        try:
            with open(_PROVINCES_FALLBACK_FILE, encoding="utf-8") as f:
                raw = json.load(f)
                return cast(list[dict[str, Any]], raw)
        except Exception as e:
            log.warning("Khong the doc vietnam_provinces.json: %s", e)
    return []


def _load_districts_fallback() -> dict[str, list[dict[str, Any]]]:
    if _DISTRICTS_FALLBACK_FILE.exists():
        try:
            with open(_DISTRICTS_FALLBACK_FILE, encoding="utf-8") as f:
                raw = json.load(f)
                return cast(dict[str, list[dict[str, Any]]], raw)
        except Exception as e:
            log.warning("Khong the doc vietnam_districts_fallback.json: %s", e)
    return {}


def get_provinces() -> list[dict[str, Any]]:
    """Lấy danh sách 63 tỉnh/thành phố trực thuộc TW tại Việt Nam."""
    global _PROVINCES_CACHE
    if _PROVINCES_CACHE is not None:
        return _PROVINCES_CACHE

    url = "https://provinces.open-api.vn/api/p/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NhipQuan-StoreConfig/1.0"})
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            simplified = [
                {
                    "code": int(p["code"]),
                    "name": str(p["name"]).strip(),
                    "division_type": str(p.get("division_type") or "").strip(),
                }
                for p in data
                if "code" in p and "name" in p
            ]
            if simplified:
                _PROVINCES_CACHE = simplified
                return simplified
    except Exception as e:
        log.info("Khong the goi open-api.vn cho tinh thanh: %s, dung fallback", e)

    fallback = _load_provinces_fallback()
    if fallback:
        _PROVINCES_CACHE = fallback
        return fallback
    return []


def get_districts(province_code: int) -> list[dict[str, Any]]:
    """Lấy danh sách quận/huyện/thị xã theo mã tỉnh/thành."""
    if province_code in _DISTRICTS_CACHE:
        return _DISTRICTS_CACHE[province_code]

    url = f"https://provinces.open-api.vn/api/p/{province_code}?depth=2"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NhipQuan-StoreConfig/1.0"})
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            districts = data.get("districts") or []
            simplified = [
                {
                    "code": int(d["code"]),
                    "name": str(d["name"]).strip(),
                    "province_code": province_code,
                    "division_type": str(d.get("division_type") or "").strip(),
                }
                for d in districts
                if "code" in d and "name" in d
            ]
            if simplified:
                _DISTRICTS_CACHE[province_code] = simplified
                return simplified
    except Exception as e:
        log.info("Khong the goi open-api.vn cho quan huyen (code=%s): %s", province_code, e)

    fallback_dict = _load_districts_fallback()
    res = fallback_dict.get(str(province_code)) or []
    if res:
        _DISTRICTS_CACHE[province_code] = res
    return res


def get_wards(district_code: int) -> list[dict[str, Any]]:
    """Lấy danh sách phường/xã/thị trấn theo mã quận/huyện."""
    if district_code in _WARDS_CACHE:
        return _WARDS_CACHE[district_code]

    url = f"https://provinces.open-api.vn/api/d/{district_code}?depth=2"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NhipQuan-StoreConfig/1.0"})
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            wards = data.get("wards") or []
            simplified = [
                {
                    "code": int(w["code"]),
                    "name": str(w["name"]).strip(),
                    "district_code": district_code,
                    "division_type": str(w.get("division_type") or "").strip(),
                }
                for w in wards
                if "code" in w and "name" in w
            ]
            _WARDS_CACHE[district_code] = simplified
            return simplified
    except Exception as e:
        log.info("Khong the goi open-api.vn cho phuong xa (code=%s): %s", district_code, e)

    return []


def geocode_address(
    address: str = "",
    *,
    phuong_xa: str = "",
    quan_huyen: str = "",
    tinh: str = "",
) -> dict[str, Any] | None:
    """Giải mã địa chỉ thành toạ độ lat/lon (Nominatim OSM -> Open-Meteo)."""
    candidates: list[str] = []
    addr_clean = address.strip()
    if addr_clean:
        candidates.append(addr_clean)

    # Tổ hợp các cấp hành chính
    parts_full = [p.strip() for p in (phuong_xa, quan_huyen, tinh) if p and p.strip()]
    if parts_full:
        c_full = ", ".join(parts_full)
        if c_full not in candidates:
            candidates.append(c_full)

    parts_dist = [p.strip() for p in (quan_huyen, tinh) if p and p.strip()]
    if parts_dist:
        c_dist = ", ".join(parts_dist)
        if c_dist not in candidates:
            candidates.append(c_dist)

    if tinh and tinh.strip() and tinh.strip() not in candidates:
        candidates.append(tinh.strip())

    for cand in candidates:
        # Thêm Việt Nam nếu chưa có
        query = f"{cand}, Việt Nam" if "việt" not in cand.lower() and "vietnam" not in cand.lower() else cand

        # 1. Thử OSM Nominatim
        try:
            qs = urllib.parse.urlencode({"q": query, "format": "json", "limit": 1, "countrycodes": "vn"})
            url = f"https://nominatim.openstreetmap.org/search?{qs}"
            req = urllib.request.Request(url, headers={"User-Agent": "NhipQuan-Geo/1.0 (ops@nhipquan.local)"})
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list) and data:
                    hit = data[0]
                    return {
                        "lat": round(float(hit["lat"]), 6),
                        "lon": round(float(hit["lon"]), 6),
                        "display_name": hit.get("display_name", ""),
                        "source": "osm",
                    }
        except Exception:
            pass

        # 2. Thử Open-Meteo Geocoding
        try:
            qs = urllib.parse.urlencode({
                "name": cand,
                "count": 1,
                "language": "vi",
                "format": "json",
                "countryCode": "VN",
            })
            url = f"https://geocoding-api.open-meteo.com/v1/search?{qs}"
            req = urllib.request.Request(url, headers={"User-Agent": "NhipQuan-Geo/1.0"})
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("results") if isinstance(data, dict) else None
                if isinstance(results, list) and results:
                    hit = results[0]
                    return {
                        "lat": round(float(hit["latitude"]), 6),
                        "lon": round(float(hit["longitude"]), 6),
                        "display_name": hit.get("name", ""),
                        "source": "open-meteo",
                    }
        except Exception:
            pass

    return None

