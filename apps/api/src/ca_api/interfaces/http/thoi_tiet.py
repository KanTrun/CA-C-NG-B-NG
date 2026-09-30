"""HTTP — AI FORECAST thời tiết hôm nay theo địa chỉ quán."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, Query

from ca_api.interfaces.http.sprint3 import _require_role
from ca_api.services.thoi_tiet import get_thoi_tiet_hom_nay

router = APIRouter(tags=["thoi_tiet"])


@router.get("/api/v1/thoi-tiet/hom-nay")
def thoi_tiet_hom_nay(
    authorization: Annotated[str | None, Header()] = None,
    force: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    """Thời tiết hôm nay + ảnh hưởng quán (Open-Meteo).

    Auth giống `/hom-nay`: mọi vai đã đăng nhập đều đọc được.
    `force=true` bỏ cache 20 phút (dùng khi vừa cập nhật địa chỉ quán).
    """
    _require_role(authorization)
    return get_thoi_tiet_hom_nay(force_refresh=force)
