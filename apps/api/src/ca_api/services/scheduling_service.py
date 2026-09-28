"""Authorized application boundary for authoritative weekly scheduling."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from ca_api.persist import (
    authoritative_assignments_replace,
    availability_confirmed_list,
    open_shift_create,
    open_shift_resolve_for_week,
    schedule_run_create,
    schedule_run_get,
    schedule_run_update_result,
)


def run_authoritative_schedule(
    *, store_id: str, tuan_iso: str, actor_id: str, idempotency_key: str,
    expected_fingerprint: str | None = None, extra_pin: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Run the one production CP-SAT path and persist its immutable input run."""
    snapshot, fingerprint = authoritative_input_fingerprint(store_id, tuan_iso)
    availability = snapshot["availability"]
    if expected_fingerprint and expected_fingerprint != fingerprint:
        raise ValueError("stale_schedule_fingerprint")
    run = schedule_run_create(
        store_id=store_id,
        tuan_iso=tuan_iso,
        input_snapshot=snapshot,
        fingerprint=fingerprint,
        idempotency_key=idempotency_key,
        created_by=actor_id,
        status="running",
    )
    if run.get("reused"):
        if run.get("fingerprint") != fingerprint:
            raise ValueError("idempotency_key_input_changed")
        persisted = schedule_run_get(str(run["id"]))
        return persisted or run

    # Lazy import keeps the legacy input adapter isolated while this service
    # remains the only authoritative scheduling application boundary.
    from ca_api.services.solver_adapter import run_solver

    result = run_solver(tuan_iso, confirmed_availability=availability, extra_pin=extra_pin)
    final_status = "computed" if result.get("ok") else "needs_gap_resolution"
    schedule_run_update_result(
        str(run["id"]), status=final_status, result_snapshot=result,
    )
    authoritative_assignments_replace(
        schedule_run_id=str(run["id"]), store_id=store_id, tuan_iso=tuan_iso,
        assignments=result.get("phan_cong") or {},
    )
    if not result.get("ok"):
        deadline_minutes = int(os.environ.get("OPEN_SHIFT_SLA_MINUTES", "120"))
        deadline = (datetime.now(UTC) + timedelta(minutes=deadline_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for gap in result.get("danh_sach_xung_dot") or []:
            ca_id = _gap_ca_id(str(gap))
            if ca_id:
                open_shift_create(
                    store_id=store_id, schedule_run_id=str(run["id"]),
                    tuan_iso=tuan_iso, ca_id=ca_id, deadline_at=deadline,
                )
    else:
        open_shift_resolve_for_week(store_id, tuan_iso)
    return {**run, "status": final_status, "result": result}


def authoritative_input_fingerprint(store_id: str, tuan_iso: str) -> tuple[dict[str, Any], str]:
    rows = availability_confirmed_list(store_id, tuan_iso)
    availability: dict[str, dict[str, list[str]]] = {}
    latest_by_employee: dict[str, dict[str, Any]] = {}
    for row in rows:
        # The employee id is the only identity key; names never enter this map.
        employee_id = str(row["nv_id"])
        previous = latest_by_employee.get(employee_id)
        if previous is None or str(row["updated_at"]) > str(previous["updated_at"]):
            latest_by_employee[employee_id] = row
    for employee_id, row in latest_by_employee.items():
        availability[employee_id] = row["availability"]
    snapshot = {"store_id": store_id, "tuan_iso": tuan_iso, "availability": availability}
    fingerprint = hashlib.sha256(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return snapshot, fingerprint


def _gap_ca_id(gap: str) -> str | None:
    """Extract the stable shift id emitted by the solver gap report."""
    marker = "Ca "
    if marker not in gap:
        return None
    # The gap format is "Ca {ca_id} ({thu} {start}-{end}) ...". The ca_id is
    # the token right after "Ca " and before the following " (" separator.
    value = gap.split(marker, 1)[1].split(" (", 1)[0].strip(" :")
    return value or None


def current_open_shifts(
    store_id: str, tuan_iso: str, *,
    phan_cong: dict[str, list[str]] | None = None,
    ca_list: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Ca thiếu người THẬT của tuần: chỉ thuộc lần xếp gần nhất và CHƯA được lấp.

    `open_shifts` là bảng SQLite TÍCH LUỸ: ca thiếu của lần xếp thất bại cũ vẫn
    nằm ở trạng thái "open" dù lần xếp sau đã đủ người (đường vá chỉ chạy khi
    lần xếp đạt). Không lọc thì mọi bề mặt (lịch tuần, chợ đổi ca) hiện hàng
    trăm ca "thiếu" không còn đúng sự thật, bắt người dùng xử lý vô nghĩa.

    Hai luật:
    1. Chỉ giữ ca của `schedule_run` MỚI NHẤT (lần xếp đang hiển thị).
    2. Nếu có `phan_cong` + `ca_list`: bỏ ca đã ĐỦ người (đã ghim thủ công hoặc
       lần xếp sau đã lấp) — ca không còn thiếu thì không còn là việc phải làm.
    """
    from ca_api.persist import open_shift_list, schedule_run_latest

    items = [
        *open_shift_list(store_id, tuan_iso=tuan_iso),
        *open_shift_list(store_id, tuan_iso=tuan_iso, status="claimed"),
    ]
    if not items:
        return []
    run = schedule_run_latest(store_id, tuan_iso)
    if not run:
        return []
    run_id = str(run.get("id") or "")
    items = [s for s in items if str(s.get("schedule_run_id") or "") == run_id]
    if phan_cong and ca_list:
        toi_thieu = {
            str(shift.get("id")): int(shift.get("so_nguoi_toi_thieu") or 1)
            for shift in ca_list
        }
        items = [
            s for s in items
            if len(set(phan_cong.get(str(s.get("ca_id") or ""), [])))
            < toi_thieu.get(str(s.get("ca_id") or ""), 1)
        ]
    return items


def resolve_schedule_gaps(
    *, store_id: str, tuan_iso: str, actor_id: str, schedule_run_id: str,
    expected_fingerprint: str, idempotency_key: str,
    ca_id: str | None = None, nv_id: str | None = None,
) -> dict[str, Any]:
    current = schedule_run_get(schedule_run_id)
    if not current or current["store_id"] != store_id or current["tuan_iso"] != tuan_iso:
        raise LookupError("schedule_run_not_found")
    # Derive the idempotency key from the pin so a different pin produces a
    # different run instead of silently reusing the previous (unpinned) one.
    pin = (ca_id, nv_id) if ca_id and nv_id else None
    pin_suffix = f":pin:{ca_id}:{nv_id}" if pin else ""
    return run_authoritative_schedule(
        store_id=store_id, tuan_iso=tuan_iso, actor_id=actor_id,
        idempotency_key=f"{idempotency_key}{pin_suffix}",
        expected_fingerprint=expected_fingerprint,
        extra_pin=pin,
    )