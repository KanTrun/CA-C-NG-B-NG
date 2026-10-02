"""Nạp lại danh mục địa chính 2 cấp (Tỉnh/Thành -> Phường/Xã) từ provinces.open-api.vn/api/v2.

Bản v2 là bản sau sáp nhập tỉnh 07/2025: 34 tỉnh/thành + 3.321 xã/phường,
chính quyền 2 cấp nên không còn cấp Quận/Huyện.

Ghi 2 file fallback dùng bởi ca_api.services.dia_chi_service:
  - vietnam_provinces.json     danh sách 34 tỉnh/thành
  - vietnam_wards_fallback.json xã/phường nhóm theo mã tỉnh

Chạy: python scripts/refresh_dia_chi.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

API_BASE = "https://provinces.open-api.vn/api/v2"
USER_AGENT = "NhipQuan-StoreConfig/1.0"
EXPECTED_PROVINCES = 34
EXPECTED_WARDS = 3321

SVC_DIR = Path(__file__).resolve().parents[1] / "apps" / "api" / "src" / "ca_api" / "services"
PROVINCES_FILE = SVC_DIR / "vietnam_provinces.json"
WARDS_FILE = SVC_DIR / "vietnam_wards_fallback.json"
LEGACY_DISTRICTS_FILE = SVC_DIR / "vietnam_districts_fallback.json"


def _get(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _dump(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raw_provinces = _get(f"{API_BASE}/")
    if not isinstance(raw_provinces, list) or not raw_provinces:
        print("API v2 khong tra ve danh sach tinh", file=sys.stderr)
        return 1

    provinces = [
        {
            "code": int(p["code"]),
            "name": str(p["name"]).strip(),
            "division_type": str(p.get("division_type") or "").strip(),
        }
        for p in raw_provinces
        if "code" in p and "name" in p
    ]
    provinces.sort(key=lambda p: p["code"])

    wards_by_province: dict[str, list[dict[str, object]]] = {}
    total_wards = 0
    for p in provinces:
        detail = _get(f"{API_BASE}/p/{p['code']}?depth=2")
        wards = (detail or {}).get("wards") or []
        simplified = [
            {
                "code": int(w["code"]),
                "name": str(w["name"]).strip(),
                "province_code": int(p["code"]),
                "division_type": str(w.get("division_type") or "").strip(),
            }
            for w in wards
            if "code" in w and "name" in w
        ]
        wards_by_province[str(p["code"])] = simplified
        total_wards += len(simplified)
        print(f"  {p['code']:>3} {p['name']:<34} {len(simplified):>4} xa/phuong")

    print(f"tinh: {len(provinces)} (ky vong {EXPECTED_PROVINCES})")
    print(f"xa/phuong: {total_wards} (ky vong {EXPECTED_WARDS})")
    if len(provinces) != EXPECTED_PROVINCES:
        print("SO TINH LECH — khong ghi file", file=sys.stderr)
        return 1
    if total_wards != EXPECTED_WARDS:
        print("SO XA/PHUONG LECH — khong ghi file", file=sys.stderr)
        return 1

    _dump(PROVINCES_FILE, provinces)
    _dump(WARDS_FILE, wards_by_province)
    if LEGACY_DISTRICTS_FILE.exists():
        LEGACY_DISTRICTS_FILE.unlink()
        print(f"da xoa {LEGACY_DISTRICTS_FILE.name} (cap quan/huyen het hieu luc)")

    print(f"da ghi {PROVINCES_FILE.name}, {WARDS_FILE.name} (ngay_cap_nhat={date.today().isoformat()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
