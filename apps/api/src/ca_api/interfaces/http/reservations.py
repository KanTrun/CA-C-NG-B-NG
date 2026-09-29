"""Reservation Management Endpoints for Store Managers and Shift Staff.

Phân quyền (khớp UI `/page-quan/dat-ban` — `session.ts` chặn `/page-quan/*`
với `nhan_vien`):

- Nghiệp vụ đặt bàn (sơ đồ bàn, danh sách/chi tiết đơn, đổi trạng thái): chỉ
  `quan_ly`/`chu_quan`. Dữ liệu trả về gồm tên và SĐT khách.
- Thông báo ca trực (`notifications/me`, `notifications/{id}/ack`): mọi vai trò
  đã đăng nhập. `resolve_shift_manager_and_backup` có thể chọn nhân viên làm
  người trực, nên nhân viên phải tự đọc và xác nhận thông báo của chính mình.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from ca_api.interfaces.http.sprint3 import _nv_from_token, _require_manager
from ca_api.persist import (
    reservation_get,
    reservation_list,
    reservation_update_status,
    table_list,
    thong_bao_ca_ack,
    thong_bao_ca_list,
)

router = APIRouter()


class CancelBody(BaseModel):
    reason: str = Field(default="Khách hủy hoặc không liên lạc được")


class CreateReservationBody(BaseModel):
    """Đơn đặt bàn do quản lý tạo tại quầy (khách gọi điện / khách tới trực tiếp)."""

    customer_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=1, max_length=40)
    booking_time: str = Field(min_length=1, description="ISO hoặc YYYY-MM-DD HH:MM (giờ ICT)")
    party_size: int = Field(ge=1, le=20)
    duration_minutes: int = Field(default=120, ge=15, le=480)
    email: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=1000)


def _kiem_thoi_gian_dat_ban(raw: str) -> None:
    """Chặn thời gian đặt bàn vô lý: quá khứ xa và quá xa tương lai.

    Bug QA đợt 5: POST với `booking_time='2020-01-01 19:00'` vẫn tạo đơn
    `confirmed` — đơn quá khứ nằm lẫn trong danh sách đang phục vụ, làm sai
    cả sơ đồ bàn lẫn báo cáo. Cho phép lùi 15 phút để bù lệch đồng hồ khi
    khách tới trực tiếp và quản lý nhập ngay sau giờ hẹn.
    """
    # Giờ quán (ICT). Không có offset trong chuỗi thì hiểu theo ICT — cùng quy
    # ước với `ngay_hom_nay_vn()` trong `context_providers`.
    vn_tz = timezone(timedelta(hours=7))
    text = raw.strip().replace("Z", "+00:00")
    try:
        moc = datetime.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"du_lieu_khong_hop_le: {exc}"
        ) from exc
    moc = moc.replace(tzinfo=vn_tz) if moc.tzinfo is None else moc.astimezone(vn_tz)
    now = datetime.now(vn_tz)
    if moc < now - timedelta(minutes=15):
        raise HTTPException(status_code=422, detail="thoi_gian_dat_ban_da_qua")
    if moc > now + timedelta(days=365):
        raise HTTPException(status_code=422, detail="thoi_gian_dat_ban_qua_xa")


@router.get("/api/v1/reservations")
def get_reservations(
    date: Annotated[str | None, Query(description="Lọc theo ngày YYYY-MM-DD")] = None,
    status: Annotated[str | None, Query(description="Lọc theo trạng thái")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Danh sách đơn đặt bàn của quán."""
    _require_manager(authorization)
    items = reservation_list(store_id="quan_01", date=date, status=status, limit=limit)
    return {"ok": True, "items": items, "total": len(items)}


@router.post("/api/v1/reservations")
def create_reservation(
    body: CreateReservationBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Tạo đơn đặt bàn thủ công (quản lý nhập tại quầy).

    Dùng lại `atomic_hold_or_book_table` nên vẫn đi qua khoá chống trùng bàn và
    thuật toán ghép bàn — không có đường tắt ghi thẳng DB. `source` được đánh
    `staff_manual` để phân biệt với đơn do AI tạo.
    """
    from ca_api.services.table_reservation_service import (
        NoTableAvailableError,
        TableReservationError,
        atomic_hold_or_book_table,
    )

    _require_manager(authorization)
    nv_id = _nv_from_token(authorization)
    _kiem_thoi_gian_dat_ban(body.booking_time)

    try:
        res = atomic_hold_or_book_table(
            psid=f"staff_{nv_id}",
            customer_name=body.customer_name,
            phone=body.phone,
            email=body.email,
            booking_time=body.booking_time,
            party_size=body.party_size,
            duration_minutes=body.duration_minutes,
            notes=body.notes,
            source="staff_manual",
            status="confirmed",
        )
    except NoTableAvailableError as e:
        raise HTTPException(status_code=409, detail=f"het_ban: {e}") from e
    except (TableReservationError, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"du_lieu_khong_hop_le: {e}") from e

    return {"ok": True, "reservation": res}


@router.get("/api/v1/reservations/tables")
def get_tables(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Danh sách sơ đồ bàn của quán."""
    _require_manager(authorization)
    tables = table_list(store_id="quan_01")
    return {"ok": True, "tables": tables}


@router.get("/api/v1/reservations/{res_id}")
def get_reservation_detail(
    res_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Xem chi tiết một đơn đặt bàn."""
    _require_manager(authorization)
    res = reservation_get(res_id)
    if not res:
        raise HTTPException(status_code=404, detail="reservation_not_found")
    return {"ok": True, "reservation": res}


@router.post("/api/v1/reservations/{res_id}/check-in")
def check_in_reservation(
    res_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Đánh dấu khách đã đến nhận bàn (seated)."""
    # `_require_manager` trả về ROLE; `actor` của lịch sử phải là nv_id thật.
    _require_manager(authorization)
    nv_id = _nv_from_token(authorization)
    success = reservation_update_status(
        res_id, new_status="seated", actor=nv_id, reason="Khách đã đến nhận bàn"
    )
    if not success:
        raise HTTPException(status_code=404, detail="reservation_not_found")
    return {"ok": True, "status": "seated"}


@router.post("/api/v1/reservations/{res_id}/no-show")
def mark_no_show_reservation(
    res_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Đánh dấu khách không đến (no_show)."""
    _require_manager(authorization)
    nv_id = _nv_from_token(authorization)
    success = reservation_update_status(
        res_id,
        new_status="no_show",
        actor=nv_id,
        reason="Quá giờ hẹn 15 phút khách không đến",
    )
    if not success:
        raise HTTPException(status_code=404, detail="reservation_not_found")
    return {"ok": True, "status": "no_show"}


@router.post("/api/v1/reservations/{res_id}/complete")
def complete_reservation(
    res_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Đánh dấu bữa ăn/uống hoàn tất, giải phóng bàn."""
    _require_manager(authorization)
    nv_id = _nv_from_token(authorization)
    success = reservation_update_status(
        res_id, new_status="completed", actor=nv_id, reason="Khách dùng xong và thanh toán"
    )
    if not success:
        raise HTTPException(status_code=404, detail="reservation_not_found")
    return {"ok": True, "status": "completed"}


@router.post("/api/v1/reservations/{res_id}/cancel")
def cancel_reservation(
    res_id: str,
    body: CancelBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Hủy đặt bàn bởi nhân viên."""
    _require_manager(authorization)
    nv_id = _nv_from_token(authorization)
    success = reservation_update_status(
        res_id,
        new_status="cancelled",
        actor=nv_id,
        reason=body.reason,
        cancelled_by="staff",
    )
    if not success:
        raise HTTPException(status_code=404, detail="reservation_not_found")
    return {"ok": True, "status": "cancelled"}


@router.get("/api/v1/reservations/notifications/me")
def get_my_notifications(
    unread_only: bool = False,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Danh sách thông báo ca trực của nhân viên hiện tại.

    Cố ý chỉ cần token (không cần quyền quản lý): người trực nhận thông báo có
    thể là nhân viên, và ai cũng chỉ đọc được thông báo gửi cho chính mình.
    """
    nv_id = _nv_from_token(authorization)
    items = thong_bao_ca_list(nv_id=nv_id, unread_only=unread_only, store_id="quan_01")
    return {"ok": True, "notifications": items}


@router.post("/api/v1/reservations/notifications/{thong_bao_id}/ack")
def ack_notification(
    thong_bao_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Ca trực xác nhận đã xem thông báo đặt bàn của chính mình."""
    nv_id = _nv_from_token(authorization)
    success = thong_bao_ca_ack(thong_bao_id, nv_id)
    return {"ok": success}


@router.get("/api/v1/reservations-metrics")
def get_reservation_metrics(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Các chỉ số thống kê đặt bàn của quán."""
    _require_manager(authorization)
    all_res = reservation_list(store_id="quan_01", limit=1000)
    total = len(all_res)
    by_status: dict[str, int] = {}
    for r in all_res:
        st = r.get("status", "unknown")
        by_status[st] = by_status.get(st, 0) + 1

    return {
        "ok": True,
        "total": total,
        "by_status": by_status,
        "confirmed": by_status.get("confirmed", 0),
        "seated": by_status.get("seated", 0),
        "completed": by_status.get("completed", 0),
        "cancelled": by_status.get("cancelled", 0),
        "no_show": by_status.get("no_show", 0),
    }
