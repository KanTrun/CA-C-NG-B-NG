"""API danh mục địa chính Việt Nam (Tỉnh/Thành, Quận/Huyện, Phường/Xã) cho hồ sơ quán."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header

from ca_api.interfaces.http.sprint3 import _require_role
from ca_api.services.dia_chi_service import get_districts, get_provinces, get_wards

router = APIRouter(tags=["dia_chi"])


@router.get("/api/v1/geo/provinces")
def api_get_provinces(
    authorization: Annotated[str | None, Header()] = None,
) -> list[dict[str, Any]]:
    """Danh sách 63 tỉnh/thành phố trực thuộc TW tại Việt Nam."""
    _require_role(authorization)
    return get_provinces()


@router.get("/api/v1/geo/districts/{province_code}")
def api_get_districts(
    province_code: int,
    authorization: Annotated[str | None, Header()] = None,
) -> list[dict[str, Any]]:
    """Danh sách quận/huyện theo mã tỉnh/thành."""
    _require_role(authorization)
    return get_districts(province_code)


@router.get("/api/v1/geo/wards/{district_code}")
def api_get_wards(
    district_code: int,
    authorization: Annotated[str | None, Header()] = None,
) -> list[dict[str, Any]]:
    """Danh sách phường/xã theo mã quận/huyện."""
    _require_role(authorization)
    return get_wards(district_code)
