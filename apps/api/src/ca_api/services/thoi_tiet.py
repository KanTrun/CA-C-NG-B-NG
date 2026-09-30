"""AI FORECAST — thời tiết hôm nay theo địa chỉ quán (Open-Meteo).

Lớp này cung cấp tín hiệu thời tiết THẬT (không bịa) cho `/hom-nay` và
Quánverse. Số liệu khí tượng lấy từ Open-Meteo (không cần API key — khớp mục
10.3 hồ sơ tổng thể). Ảnh hưởng quán là quy tắc TẤT ĐỊNH, không gọi LLM.

Khi quán chưa cấu hình địa chỉ / tỉnh / thành phố → `co_du_lieu: false`.
Không fallback sang thành phố giả (ADR-008).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from ca_api.services.store_public_context import get_store_profile

log = logging.getLogger("ca_api.thoi_tiet")

_VN_TZ = timezone(timedelta(hours=7))
_CACHE_TTL_S = 20 * 60  # 20 phút
_CACHE_KEY = "thoi_tiet_hom_nay_cache"
_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_HTTP_TIMEOUT_S = 8

# WMO Weather interpretation codes → nhóm UI tiếng Việt.
# https://open-meteo.com/en/docs
_WMO_GROUPS: dict[int, tuple[str, str]] = {
    0: ("nang", "Trời quang"),
    1: ("nang", "Chủ yếu nắng"),
    2: ("may", "Mây rải rác"),
    3: ("may", "U ám"),
    45: ("suong", "Sương mù"),
    48: ("suong", "Sương giá"),
    51: ("mua", "Mưa phùn nhẹ"),
    53: ("mua", "Mưa phùn"),
    55: ("mua", "Mưa phùn dày"),
    56: ("mua", "Mưa phùn lạnh"),
    57: ("mua", "Mưa phùn lạnh dày"),
    61: ("mua", "Mưa nhẹ"),
    63: ("mua", "Mưa vừa"),
    65: ("mua_to", "Mưa to"),
    66: ("mua", "Mưa lạnh"),
    67: ("mua_to", "Mưa lạnh to"),
    71: ("mua", "Tuyết nhẹ"),
    73: ("mua", "Tuyết vừa"),
    75: ("mua_to", "Tuyết dày"),
    77: ("mua", "Hạt tuyết"),
    80: ("mua", "Mưa rào nhẹ"),
    81: ("mua", "Mưa rào"),
    82: ("mua_to", "Mưa rào rất to"),
    85: ("mua", "Mưa tuyết"),
    86: ("mua_to", "Mưa tuyết to"),
    95: ("bao", "Dông"),
    96: ("bao", "Dông kèm mưa đá nhẹ"),
    99: ("bao", "Dông kèm mưa đá"),
}


def weather_group(code: int | None) -> tuple[str, str]:
    """Map WMO code → (nhom_ui, mo_ta_vi). Không biết → mây."""
    if code is None:
        return ("may", "Chưa rõ")
    return _WMO_GROUPS.get(int(code), ("may", f"Mã thời tiết {code}"))


def _http_get_json(url: str) -> dict[str, Any] | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NhipQuan/1.0 (thoi-tiet)"})
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        log.warning("thoi_tiet http that bai: %s — %s", url.split("?", 1)[0], exc)
        return None


def resolve_vi_tri(profile: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Geocode vị trí quán từ tinh/thanh_pho hoặc dia_chi.

    Trả dict `{thanh_pho, tinh, lat, lon, nguon}` hoặc `None` khi thiếu dữ liệu.
    Thử nhiều query (tỉnh → thành+tỉnh → địa chỉ) vì Open-Meteo có thể không
    nhận "Quận 1, Hồ Chí Minh" trong khi nhận "Hồ Chí Minh".
    """
    p = profile if isinstance(profile, dict) else get_store_profile()
    thanh_pho = str(p.get("thanh_pho") or "").strip()
    tinh = str(p.get("tinh") or "").strip()
    dia_chi = str(p.get("dia_chi") or "").strip()

    candidates: list[tuple[str, str]] = []
    if tinh:
        candidates.append((f"{tinh}, Việt Nam", "tinh_thanh"))
    if thanh_pho and tinh:
        candidates.append((f"{thanh_pho}, {tinh}, Việt Nam", "tinh_thanh"))
    if thanh_pho and not tinh:
        candidates.append((f"{thanh_pho}, Việt Nam", "tinh_thanh"))
    if dia_chi:
        q = f"{dia_chi}, Việt Nam" if "việt" not in dia_chi.lower() and "vietnam" not in dia_chi.lower() else dia_chi
        candidates.append((q, "dia_chi"))
    if not candidates:
        return None

    for query, nguon in candidates:
        hit = _geocode_once(query)
        if hit is None:
            continue
        try:
            lat = float(hit["latitude"])
            lon = float(hit["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        name = str(hit.get("name") or thanh_pho or "").strip()
        admin1 = str(hit.get("admin1") or tinh or "").strip()
        return {
            "thanh_pho": thanh_pho or name,
            "tinh": tinh or admin1,
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "nguon": nguon,
            "query": query,
        }
    return None


def _geocode_once(query: str) -> dict[str, Any] | None:
    """Một lần geocode; thử có countryCode=VN rồi không ép nếu rỗng."""
    qs = urllib.parse.urlencode(
        {
            "name": query,
            "count": 1,
            "language": "vi",
            "format": "json",
            "countryCode": "VN",
        }
    )
    data = _http_get_json(f"{_GEOCODE_URL}?{qs}")
    results = (data or {}).get("results") if data else None
    if not isinstance(results, list) or not results:
        qs2 = urllib.parse.urlencode({"name": query, "count": 1, "language": "vi", "format": "json"})
        data = _http_get_json(f"{_GEOCODE_URL}?{qs2}")
        results = (data or {}).get("results") if data else None
    if not isinstance(results, list) or not results:
        return None
    hit = results[0]
    return hit if isinstance(hit, dict) else None

def _anh_huong_quan(
    *,
    nhom: str,
    nhiet_do: float | None,
    mua_mm: float | None,
    mo_ta: str,
) -> dict[str, Any]:
    """Quy tắc deterministic: thời tiết → ảnh hưởng vận hành quán."""
    yeu_to: list[str] = []
    de_xuat_mode: str | None = None
    he_so_ngoai_troi = 1.0
    tone = "default"

    mua = float(mua_mm or 0)
    temp = float(nhiet_do) if nhiet_do is not None else None

    if nhom in {"mua_to", "bao"} or mua >= 5:
        yeu_to.extend(
            [
                "Khách khu ngoài trời giảm mạnh — ưu tiên chỗ trong nhà.",
                "Nhu cầu món nóng (cà phê, trà) có xu hướng tăng.",
                "Chuẩn bị khăn/ô gần cửa và kiểm tra hàng đợi quầy.",
            ]
        )
        de_xuat_mode = "troi_mua"
        he_so_ngoai_troi = 0.45
        tone = "warn"
        tom_tat = f"{mo_ta}: dồn chỗ trong nhà, ưu tiên món nóng."
    elif nhom == "mua" or mua >= 0.5:
        yeu_to.extend(
            [
                "Khách ngoài trời giảm — giữ bàn trong nhà sẵn sàng.",
                "Gợi ý món nóng trên menu / bảng khuyến mãi.",
            ]
        )
        de_xuat_mode = "troi_mua"
        he_so_ngoai_troi = 0.7
        tone = "warn"
        tom_tat = f"{mo_ta}: khách ngoài trời thưa hơn, cân nhắc bật chế độ Trời mưa."
    elif nhom == "nang" and temp is not None and temp >= 33:
        yeu_to.extend(
            [
                "Nắng nóng — đồ uống lạnh / đá có thể tăng.",
                "Khu ngoài trời có bóng râm dễ đông hơn.",
            ]
        )
        he_so_ngoai_troi = 1.15
        tone = "ok"
        tom_tat = f"{mo_ta}: ưu tiên món mát, kiểm tra đá và chỗ ngồi ngoài trời."
    elif nhom == "nang":
        yeu_to.append("Trời đẹp — khu ngoài trời thường đông hơn giờ thường.")
        he_so_ngoai_troi = 1.1
        tone = "ok"
        tom_tat = f"{mo_ta}: giữ nhịp phục vụ ổn định, chú ý khu ngoài trời."
    elif nhom == "suong":
        yeu_to.append("Sương mù — khách có thể đến muộn hơn buổi sáng.")
        he_so_ngoai_troi = 0.9
        tom_tat = f"{mo_ta}: ca sáng có thể chậm hơn bình thường."
    else:
        yeu_to.append("Thời tiết trung tính — theo dõi tải quầy theo lịch sử đơn.")
        tom_tat = f"{mo_ta}: không có tín hiệu thời tiết đặc biệt cho vận hành."

    out: dict[str, Any] = {
        "tom_tat": tom_tat,
        "yeu_to": yeu_to,
        "he_so_ngoai_troi": he_so_ngoai_troi,
        "tone": tone,
    }
    if de_xuat_mode:
        out["de_xuat_mode"] = de_xuat_mode
        out["de_xuat_mode_label"] = "Trời mưa"
        out["de_xuat_mode_href"] = "/quanverse"
    return out


def _parse_forecast(data: dict[str, Any], vi_tri: dict[str, Any]) -> dict[str, Any]:
    current_raw = data.get("current")
    hourly_raw = data.get("hourly")
    current: dict[str, Any] = current_raw if isinstance(current_raw, dict) else {}
    hourly: dict[str, Any] = hourly_raw if isinstance(hourly_raw, dict) else {}

    code_now = current.get("weather_code")
    try:
        code_now_i = int(code_now) if code_now is not None else None
    except (TypeError, ValueError):
        code_now_i = None
    nhom, mo_ta = weather_group(code_now_i)

    temp_now: float | None
    try:
        temp_now = float(current["temperature_2m"]) if current.get("temperature_2m") is not None else None
    except (TypeError, ValueError):
        temp_now = None

    precip_now: float | None
    try:
        precip_now = float(current["precipitation"]) if current.get("precipitation") is not None else None
    except (TypeError, ValueError):
        precip_now = None

    times_raw = hourly.get("time")
    temps_raw = hourly.get("temperature_2m")
    codes_raw = hourly.get("weather_code")
    precips_raw = hourly.get("precipitation")
    times: list[Any] = times_raw if isinstance(times_raw, list) else []
    temps: list[Any] = temps_raw if isinstance(temps_raw, list) else []
    codes: list[Any] = codes_raw if isinstance(codes_raw, list) else []
    precips: list[Any] = precips_raw if isinstance(precips_raw, list) else []

    ngay_vn = datetime.now(_VN_TZ).date().isoformat()
    theo_gio: list[dict[str, Any]] = []
    for i, t in enumerate(times):
        if not isinstance(t, str) or not t.startswith(ngay_vn):
            continue
        try:
            gio = int(t[11:13])
        except ValueError:
            continue
        if gio < 6 or gio > 22:
            continue
        c_raw = codes[i] if i < len(codes) else None
        try:
            c_i = int(c_raw) if c_raw is not None else None
        except (TypeError, ValueError):
            c_i = None
        g_nhom, g_mo_ta = weather_group(c_i)
        t_val: float | None
        try:
            t_val = float(temps[i]) if i < len(temps) and temps[i] is not None else None
        except (TypeError, ValueError):
            t_val = None
        p_val: float | None
        try:
            p_val = float(precips[i]) if i < len(precips) and precips[i] is not None else None
        except (TypeError, ValueError):
            p_val = None
        theo_gio.append(
            {
                "gio": gio,
                "nhiet_do": t_val,
                "nhom": g_nhom,
                "mo_ta": g_mo_ta,
                "ma_thoi_tiet": c_i,
                "mua_mm": p_val,
            }
        )

    impact = _anh_huong_quan(nhom=nhom, nhiet_do=temp_now, mua_mm=precip_now, mo_ta=mo_ta)

    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    do_am: float | None
    try:
        do_am = (
            float(current["relative_humidity_2m"])
            if current.get("relative_humidity_2m") is not None
            else None
        )
    except (TypeError, ValueError):
        do_am = None
    return {
        "co_du_lieu": True,
        "vi_tri": {
            "thanh_pho": vi_tri.get("thanh_pho") or "",
            "tinh": vi_tri.get("tinh") or "",
            "lat": vi_tri.get("lat"),
            "lon": vi_tri.get("lon"),
            "nguon": vi_tri.get("nguon") or "dia_chi",
        },
        "hien_tai": {
            "nhiet_do": temp_now,
            "nhom": nhom,
            "mo_ta": mo_ta,
            "ma_thoi_tiet": code_now_i,
            "mua_mm": precip_now,
            "do_am": do_am,
        },
        "theo_gio": theo_gio,
        "anh_huong_quan": impact,
        "cap_nhat_luc": now_iso,
        "nguon": "open-meteo",
        "ngay": ngay_vn,
    }


def _empty(*, ly_do: str, can_cau_hinh: bool = False) -> dict[str, Any]:
    return {
        "co_du_lieu": False,
        "ly_do": ly_do,
        "can_cau_hinh": can_cau_hinh,
        "vi_tri": None,
        "hien_tai": None,
        "theo_gio": [],
        "anh_huong_quan": None,
        "cap_nhat_luc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "nguon": "open-meteo",
        "ngay": datetime.now(_VN_TZ).date().isoformat(),
    }


def _cache_get(store_id: str, ngay: str, lat: float, lon: float) -> dict[str, Any] | None:
    from ca_api.persist import kv_get

    raw = kv_get(_CACHE_KEY, None)
    if not isinstance(raw, dict):
        return None
    if raw.get("store_id") != store_id or raw.get("ngay") != ngay:
        return None
    if abs(float(raw.get("lat") or 0) - lat) > 0.001 or abs(float(raw.get("lon") or 0) - lon) > 0.001:
        return None
    try:
        cached_at = datetime.fromisoformat(str(raw.get("cached_at") or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if (datetime.now(UTC) - cached_at).total_seconds() > _CACHE_TTL_S:
        return None
    payload = raw.get("payload")
    return payload if isinstance(payload, dict) else None


def _cache_set(store_id: str, ngay: str, lat: float, lon: float, payload: dict[str, Any]) -> None:
    from ca_api.persist import kv_set

    kv_set(
        _CACHE_KEY,
        {
            "store_id": store_id,
            "ngay": ngay,
            "lat": lat,
            "lon": lon,
            "cached_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "payload": payload,
        },
    )


def get_thoi_tiet_hom_nay(*, store_id: str = "quan_01", force_refresh: bool = False) -> dict[str, Any]:
    """Endpoint nghiệp vụ: thời tiết hôm nay + ảnh hưởng quán."""
    profile = get_store_profile()
    thanh_pho = str(profile.get("thanh_pho") or "").strip()
    tinh = str(profile.get("tinh") or "").strip()
    dia_chi = str(profile.get("dia_chi") or "").strip()
    if not (thanh_pho or tinh or dia_chi):
        return _empty(
            ly_do="Chưa cấu hình địa chỉ quán. Vào Cấu hình quán để điền tỉnh/thành hoặc địa chỉ.",
            can_cau_hinh=True,
        )

    vi_tri = resolve_vi_tri(profile)
    if not vi_tri:
        return _empty(
            ly_do="Không xác định được vị trí từ địa chỉ quán. Kiểm tra lại tỉnh/thành hoặc địa chỉ.",
            can_cau_hinh=True,
        )

    ngay = datetime.now(_VN_TZ).date().isoformat()
    lat = float(vi_tri["lat"])
    lon = float(vi_tri["lon"])

    if not force_refresh:
        cached = _cache_get(store_id, ngay, lat, lon)
        if cached is not None:
            out = dict(cached)
            out["tu_cache"] = True
            return out

    qs = urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code",
            "hourly": "temperature_2m,precipitation,weather_code",
            "timezone": "Asia/Ho_Chi_Minh",
            "forecast_days": 1,
        }
    )
    data = _http_get_json(f"{_FORECAST_URL}?{qs}")
    if not data:
        return _empty(ly_do="Không đọc được dự báo thời tiết lúc này. Thử lại sau.")

    payload = _parse_forecast(data, vi_tri)
    payload["tu_cache"] = False
    try:
        _cache_set(store_id, ngay, lat, lon, payload)
    except Exception:  # noqa: BLE001 — cache hỏng không được làm hỏng response
        log.exception("thoi_tiet cache set that bai")
    return payload
