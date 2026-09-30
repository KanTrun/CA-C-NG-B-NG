# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Enterprise Unit & Concurrency Tests for Auto Table Reservation Engine.

Verifies:
1. Concurrency & Race condition (TOCTOU) — zero double booking with multi-threaded attempts.
2. Table combinability matrix (single fit vs combinable pair vs >8 escalation).
3. Idempotency on repeated webhook attempts.
4. Anti-abuse guard (active booking cap & no-show blacklist).
5. 2-Phase Dialog State Machine (Extracting -> Confirming -> Confirmed).
6. Customer cancellation via chat.
7. Shift manager resolution & notification dispatch.
8. Fail-closed safety fallback.
"""

from __future__ import annotations

import concurrent.futures
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from ca_api.persist import (
    _conn,
    init_db,
    reservation_create,
    reservation_find_active_by_psid,
    reservation_get,
    reservation_list,
    reservation_update_status,
    table_list,
    thong_bao_ca_list,
)
from ca_api.services.table_reservation_service import (
    ICT,
    NoTableAvailableError,
    atomic_hold_or_book_table,
    check_anti_abuse,
    customer_cancel_reservation,
    dispatch_reservation_notification,
    format_ict_iso,
    generate_reservation_idempotency_key,
    notify_backup_if_unacked,
    parse_booking_datetime,
    resolve_shift_manager_and_backup,
    send_reservation_confirmation_email,
)
from ca_agents.ag_concierge import (
    extract_reservation_entities,
    handle_reservation,
)


@pytest.fixture(autouse=True)
def setup_clean_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_reservation.db"
    monkeypatch.setenv("NHIPQUAN_DB", str(test_db))
    monkeypatch.setenv("NHIPQUAN_AUTO_RESERVATION", "1")
    init_db()
    yield


# ── 1. Table Combinability & Matching ─────────────────────────────────────────


def test_single_table_matching():
    # 2 people -> should pick a 2-seat table (B101..B104)
    res = atomic_hold_or_book_table(
        psid="psid_01",
        customer_name="Anh Tuấn",
        phone="0912345678",
        booking_time="2026-09-10T19:00:00",
        party_size=2,
    )
    assert res["status"] == "confirmed"
    assert len(res["table_ids"]) == 1
    assert res["table_ids"][0] in ("B101", "B102", "B103", "B104")


def test_combined_table_matching():
    # 7 people -> no single table can fit (max single is 4), should combine B203 + B204 (4+4=8)
    res = atomic_hold_or_book_table(
        psid="psid_02",
        customer_name="Chị Linh",
        phone="0987654321",
        booking_time="2026-09-10T19:00:00",
        party_size=7,
    )
    assert res["status"] == "confirmed"
    assert sorted(res["table_ids"]) == ["B203", "B204"]


def test_large_group_exceeds_auto_limit():
    # 12 people -> exceeds auto limit (>8), should raise NoTableAvailableError
    with pytest.raises(NoTableAvailableError):
        atomic_hold_or_book_table(
            psid="psid_03",
            customer_name="Anh Nam",
            phone="0901234567",
            booking_time="2026-09-10T19:00:00",
            party_size=12,
        )


# ── 2. Concurrency & TOCTOU Double-Booking Test ───────────────────────────────


def test_concurrency_race_condition_no_double_booking():
    # Set all tables inactive except B105 (4 seats)
    with _conn() as cx:
        cx.execute("UPDATE ban_an SET trang_thai_hoat_dong=0 WHERE id != 'B105'")

    assert len([t for t in table_list() if t["trang_thai_hoat_dong"] == 1]) == 1

    success_count = 0
    failure_count = 0

    def attempt_booking(i: int):
        try:
            res = atomic_hold_or_book_table(
                psid=f"psid_race_{i}",
                customer_name=f"Khách {i}",
                phone=f"091100000{i}",
                booking_time="2026-09-12T19:00:00",
                party_size=4,
            )
            return True, res
        except NoTableAvailableError:
            return False, None

    # Run 8 concurrent booking requests for the exact same table and time
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(attempt_booking, i) for i in range(8)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    for ok, res in results:
        if ok:
            success_count += 1
        else:
            failure_count += 1

    # Exactly 1 request must win B105, the other 7 must fail
    assert success_count == 1, f"Expected 1 winner but got {success_count}"
    assert failure_count == 7, f"Expected 7 failures but got {failure_count}"


# ── 3. Webhook Idempotency ───────────────────────────────────────────────────


def test_idempotency_repeated_webhook():
    time_str = "2026-09-15T18:30:00"
    res1 = atomic_hold_or_book_table(
        psid="psid_idem",
        customer_name="Trùng Lặp",
        phone="0933111222",
        booking_time=time_str,
        party_size=3,
    )
    # Repeated attempt with same customer and time
    res2 = atomic_hold_or_book_table(
        psid="psid_idem",
        customer_name="Trùng Lặp",
        phone="0933111222",
        booking_time=time_str,
        party_size=3,
    )
    assert res1["id"] == res2["id"]
    # Verify only 1 record exists in DB
    all_res = reservation_list()
    assert len([r for r in all_res if r["psid"] == "psid_idem"]) == 1


# ── 4. Anti-Abuse & Blacklist ────────────────────────────────────────────────


def test_anti_abuse_active_booking_cap():
    # First booking succeeds
    atomic_hold_or_book_table(
        psid="psid_abuser",
        customer_name="Khách Spam",
        phone="0944000111",
        booking_time="2026-09-16T19:00:00",
        party_size=2,
    )
    # Second booking from same PSID is blocked by anti-abuse
    allowed, reason = check_anti_abuse(psid="psid_abuser", phone="0944000111")
    assert not allowed
    assert reason == "active_booking_exists"


def test_anti_abuse_no_show_blacklist():
    # Insert 2 previous no-show records for this phone
    for i in range(2):
        res_id = reservation_create(
            {
                "psid": f"psid_old_{i}",
                "customer_name": "Khách Bùng",
                "phone": "0999888777",
                "booking_time": f"2026-09-0{i+1}T19:00:00",
                "party_size": 2,
                "table_ids": ["B101"],
                "status": "no_show",
            }
        )

    allowed, reason = check_anti_abuse(phone="0999888777")
    assert not allowed
    assert reason == "no_show_blacklist"


# ── 5. Dialog State Machine (Extracting -> Confirming -> Confirmed) ───────────


def test_dialog_state_machine_3_turns():
    psid = "psid_dialog_user"

    # Turn 1: Customer asks without time & phone
    ticket1 = handle_reservation("Cho mình đặt bàn 4 người nha", psid=psid)
    assert ticket1.action_type == "ask_info"
    assert not ticket1.requires_human_approval
    assert "mấy giờ" in ticket1.suggested_reply.lower()

    # State carried over
    session_state = ticket1.extracted_data

    # Turn 2: Customer provides time and phone
    ticket2 = handle_reservation(
        "19h tối nay nhé, sđt 0912345678, tên Hùng",
        psid=psid,
        session_state=session_state,
    )
    assert ticket2.action_type == "ask_confirmation"
    assert not ticket2.requires_human_approval
    assert "xác nhận lại thông tin" in ticket2.suggested_reply.lower()
    assert "4" in ticket2.suggested_reply
    assert "0912345678" in ticket2.suggested_reply

    # State now in CONFIRMING
    session_state = ticket2.extracted_data
    assert session_state.get("dialog_step") == "CONFIRMING"

    # Turn 3: Customer confirms "Đúng rồi em"
    ticket3 = handle_reservation(
        "Đúng rồi em ơi",
        psid=psid,
        session_state=session_state,
    )
    assert ticket3.action_type == "confirmed"
    assert not ticket3.requires_human_approval
    assert "đã xác nhận giữ bàn" in ticket3.suggested_reply.lower()

    # Check reservation in database
    actives = reservation_find_active_by_psid(psid)
    assert len(actives) == 1
    assert actives[0]["customer_name"] == "Hùng"
    assert actives[0]["party_size"] == 4


# ── 6. Cancellation via Chat ─────────────────────────────────────────────────


def test_customer_cancellation_flow():
    psid = "psid_cancel_user"
    # Create confirmed booking
    atomic_hold_or_book_table(
        psid=psid,
        customer_name="Khách Hủy",
        phone="0911223344",
        booking_time="2026-09-17T20:00:00",
        party_size=2,
    )
    assert len(reservation_find_active_by_psid(psid)) == 1

    # Customer chats "mình bận không đến được, hủy bàn giúp mình"
    ticket = handle_reservation("mình bận không đến được, hủy bàn giúp mình", psid=psid)
    assert ticket.action_type == "cancelled"
    assert "đã hủy lịch đặt bàn" in ticket.suggested_reply.lower()

    # Active reservations should now be 0
    assert len(reservation_find_active_by_psid(psid)) == 0


# ── 7. Shift Manager Resolution & Notification Dispatch ──────────────────────


def test_shift_manager_resolution_and_notification():
    dt = parse_booking_datetime("2026-09-18T19:30:00")  # Evening shift
    shift_info = resolve_shift_manager_and_backup(dt)

    assert shift_info["khung"] == "toi"
    assert shift_info["primary_nv_id"] is not None

    # Test notification dispatch
    res = {
        "id": "res_notif_test",
        "customer_name": "Bảo An",
        "phone": "0988776655",
        "booking_time": "2026-09-18T19:30:00+07:00",
        "party_size": 4,
        "table_ids": ["B105"],
        "notified_nv_id": shift_info["primary_nv_id"],
    }
    dispatch_res = dispatch_reservation_notification(res)
    assert dispatch_res["notification_id"] is not None

    # Check in database
    notifs = thong_bao_ca_list(shift_info["primary_nv_id"])
    assert any(n["dat_ban_id"] == "res_notif_test" for n in notifs)


def test_auto_reservation_disabled_flag_requires_human_approval(monkeypatch):
    monkeypatch.setenv("NHIPQUAN_AUTO_RESERVATION", "0")
    ticket = handle_reservation("Cho mình đặt bàn 4 người lúc 19h tối nay", psid="psid_off")
    assert ticket.requires_human_approval is True
    assert ticket.action_type == "needs_manager_review"
    assert "chuẩn bị bàn" in ticket.suggested_reply.lower()


# ── 8. HTTP API Endpoints Full Lifecycle & RBAC Tests ─────────────────────────


def test_reservation_http_endpoints_full_lifecycle():
    from fastapi.testclient import TestClient
    from ca_api.interfaces.http.main import app as fastapi_app
    from unit.auth_util import headers

    client = TestClient(fastapi_app)
    auth = headers(client, "lan")

    # 1. RBAC check: Unauthenticated access blocked
    unauth = client.get("/api/v1/reservations")
    assert unauth.status_code == 401

    # 2. Get tables (should return 10 seeded tables)
    r_tables = client.get("/api/v1/reservations/tables", headers=auth)
    assert r_tables.status_code == 200
    tables = r_tables.json()["tables"]
    assert len(tables) == 10
    assert any(t["id"] == "B101" for t in tables)

    # 3. Create a reservation
    res = atomic_hold_or_book_table(
        psid="psid_http_test",
        customer_name="Trần Văn Nam",
        phone="0918889999",
        booking_time="2026-09-20T19:00:00",
        party_size=4,
    )
    res_id = res["id"]

    # 4. List reservations
    r_list = client.get("/api/v1/reservations", headers=auth)
    assert r_list.status_code == 200
    items = r_list.json()["items"]
    assert any(item["id"] == res_id for item in items)

    # 5. Get detail
    r_detail = client.get(f"/api/v1/reservations/{res_id}", headers=auth)
    assert r_detail.status_code == 200
    assert r_detail.json()["reservation"]["customer_name"] == "Trần Văn Nam"

    # 6. Check-in (seated)
    r_checkin = client.post(f"/api/v1/reservations/{res_id}/check-in", headers=auth)
    assert r_checkin.status_code == 200
    assert r_checkin.json()["status"] == "seated"

    # 7. Complete (completed)
    r_complete = client.post(f"/api/v1/reservations/{res_id}/complete", headers=auth)
    assert r_complete.status_code == 200
    assert r_complete.json()["status"] == "completed"

    # 8. No-show workflow on new booking
    res2 = atomic_hold_or_book_table(
        psid="psid_http_noshow",
        customer_name="Khách Vắng",
        phone="0917778888",
        booking_time="2026-09-21T19:00:00",
        party_size=2,
    )
    r_noshow = client.post(f"/api/v1/reservations/{res2['id']}/no-show", headers=auth)
    assert r_noshow.status_code == 200
    assert r_noshow.json()["status"] == "no_show"

    # 9. Cancel workflow on new booking
    res3 = atomic_hold_or_book_table(
        psid="psid_http_cancel",
        customer_name="Khách Bận",
        phone="0916667777",
        booking_time="2026-09-22T19:00:00",
        party_size=2,
    )
    r_cancel = client.post(
        f"/api/v1/reservations/{res3['id']}/cancel",
        json={"reason": "Khách đổi kế hoạch đột xuất"},
        headers=auth,
    )
    assert r_cancel.status_code == 200
    assert r_cancel.json()["status"] == "cancelled"

    # 10. Metrics endpoint
    r_metrics = client.get("/api/v1/reservations-metrics", headers=auth)
    assert r_metrics.status_code == 200
    metrics = r_metrics.json()
    assert metrics["ok"] is True
    assert metrics["total"] >= 3
    assert metrics["completed"] >= 1
    assert metrics["no_show"] >= 1
    assert metrics["cancelled"] >= 1


def test_auto_reservation_with_gmail_confirmation_ticket():
    psid = "psid_customer_gmail"

    # Turn 1: Customer asks to book with time and party size, but no phone or Gmail
    ticket1 = handle_reservation("Cho mình đặt bàn 6 người lúc 18h tối nay nha", psid=psid)
    assert ticket1.action_type == "ask_info"
    assert not ticket1.requires_human_approval
    assert "gmail" in ticket1.suggested_reply.lower() or "email" in ticket1.suggested_reply.lower()

    session_state = ticket1.extracted_data

    # Turn 2: Customer provides phone and Gmail
    ticket2 = handle_reservation(
        "SĐT 0987654321, email: khachhang.test@example.com, tên Trang nhé",
        psid=psid,
        session_state=session_state,
    )
    # Automatic approval without manager intervention!
    assert ticket2.action_type == "confirmed"
    assert not ticket2.requires_human_approval
    assert "đã xác nhận giữ bàn" in ticket2.suggested_reply.lower()
    assert "khachhang.test@example.com" in ticket2.suggested_reply

    # Verify reservation created in database
    actives = reservation_find_active_by_psid(psid)
    assert len(actives) == 1
    booking = actives[0]
    assert booking["customer_name"] == "Trang"
    assert booking["party_size"] == 6
    assert booking["phone"] == "0987654321"
    assert "khachhang.test@example.com" in booking.get("notes", "")

    # Verify sending confirmation email works
    ok = send_reservation_confirmation_email(booking, to_email="khachhang.test@example.com")
    assert ok is True


# ── 9. Regression: shift resolution theo ca_id (không phải mã khung) ─────────


def test_resolve_shift_dung_ca_id_tu_phan_cong():
    """`phan_cong` được key theo ca_id (`w1_c01`), KHÔNG theo `T2_sang`.

    Trước đây hàm tra thẳng `phan_cong["T2_sang"]` nên luôn rỗng và mọi thông
    báo ca trực rơi về quản lý mặc định (`nv_01`). Test này ghim hành vi đúng:
    nhân viên thật trong ca phải được chọn làm người nhận thông báo.
    """
    from ca_api.persist import kv_set

    # T6 (thứ Sáu) ca tối = w1_c47..c50 theo seed `ca_mau_21`.
    # nv_05 là nhân viên, nv_02 là chủ quán → chủ quán phải làm trưởng ca.
    kv_set("phan_cong", {"w1_c47": ["nv_05"], "w1_c48": ["nv_02"]})
    try:
        shift = resolve_shift_manager_and_backup(parse_booking_datetime("2026-09-18T19:30:00"))
        assert shift["khung"] == "toi"
        assert shift["ca_id"] == "T6_toi"
        assert "w1_c47" in shift["ca_ids"]
        # Chủ quán trong ca được ưu tiên làm trưởng ca; nhân viên vào dự phòng.
        assert shift["primary_nv_id"] == "nv_02"
        assert "nv_05" in shift["backup_nv_ids"]
        # Không còn rơi về quản lý mặc định hardcode.
        assert shift["primary_nv_id"] != "nv_01" or "nv_01" in shift["backup_nv_ids"]
    finally:
        kv_set("phan_cong", {})


def test_resolve_shift_bien_khung_theo_seed():
    """Biên khung phải khớp seed (sang 07–12, chieu 12–17, toi 17–22).

    Code cũ hardcode sang 07–15 nên đơn 13:00 bị gán nhầm vào ca sáng.
    """
    assert resolve_shift_manager_and_backup(parse_booking_datetime("2026-09-14T09:00:00"))["khung"] == "sang"
    assert resolve_shift_manager_and_backup(parse_booking_datetime("2026-09-14T13:00:00"))["khung"] == "chieu"
    assert resolve_shift_manager_and_backup(parse_booking_datetime("2026-09-14T18:00:00"))["khung"] == "toi"
    # 11:59 vẫn thuộc ca sáng, 12:00 đã sang ca chiều.
    assert resolve_shift_manager_and_backup(parse_booking_datetime("2026-09-14T11:59:00"))["khung"] == "sang"
    assert resolve_shift_manager_and_backup(parse_booking_datetime("2026-09-14T12:00:00"))["khung"] == "chieu"


def test_resolve_shift_uu_tien_phan_cong_theo_tuan():
    """Phải đọc `phan_cong_by_week` của TUẦN đặt bàn, không phải key phẳng.

    `solver_adapter._week_store("phan_cong_by_week", tuần, ...)` lưu lịch theo
    tuần; key phẳng `phan_cong` chỉ giữ kết quả tuần gần nhất. Nếu chỉ đọc key
    phẳng thì đơn đặt trước cho tuần sau sẽ gửi thông báo cho người trực của
    tuần CŨ. `sprint3._phan_cong` và `sprint45._phan` đều ưu tiên by_week nên
    ở đây phải nhất quán.
    """
    from ca_api.persist import kv_set

    # 2026-09-18 là T6, tuần ISO 2026-W38.
    kv_set("phan_cong", {"w1_c47": ["nv_05"]})  # tuần CŨ
    kv_set(
        "phan_cong_by_week",
        {"2026-W38": {"w1_c47": ["nv_02"]}},  # tuần MỚI (đúng)
    )
    try:
        shift = resolve_shift_manager_and_backup(parse_booking_datetime("2026-09-18T19:30:00"))
        # nv_02 (chủ quán, tuần W38) phải thắng nv_05 (tuần cũ).
        assert shift["primary_nv_id"] == "nv_02", "phải đọc phân công theo tuần của ngày đặt bàn"
    finally:
        kv_set("phan_cong", {})
        kv_set("phan_cong_by_week", {})


def test_resolve_shift_fallback_ve_phan_cong_khi_thieu_by_week():
    """Không có dữ liệu theo tuần → dùng key phẳng (tương thích ngược)."""
    from ca_api.persist import kv_set

    kv_set("phan_cong", {"w1_c47": ["nv_05"]})
    kv_set("phan_cong_by_week", {})
    try:
        shift = resolve_shift_manager_and_backup(parse_booking_datetime("2026-09-18T19:30:00"))
        assert shift["primary_nv_id"] == "nv_05"
    finally:
        kv_set("phan_cong", {})


# ── 10. Regression: RBAC cho route đặt bàn ───────────────────────────────────


def test_reservation_routes_chan_nhan_vien():
    """Nhân viên không được đọc dữ liệu khách hay đổi trạng thái đơn.

    Trước đây route chỉ dùng `_require_role` (chỉ cần token) nên `nhan_vien`
    gọi thẳng API vẫn lấy được tên + SĐT khách và hủy đơn.
    """
    from ca_api.interfaces.http.main import app as fastapi_app
    from fastapi.testclient import TestClient

    from unit.auth_util import headers

    client = TestClient(fastapi_app)
    nv = headers(client, "minh")  # role: nhan_vien
    ql = headers(client, "lan")  # role: quan_ly

    res = atomic_hold_or_book_table(
        psid="psid_rbac_probe",
        customer_name="Khách RBAC",
        phone="0900111222",
        booking_time="2026-09-23T19:00:00",
        party_size=2,
    )

    # Nhân viên: 403 ở mọi route nghiệp vụ.
    assert client.get("/api/v1/reservations", headers=nv).status_code == 403
    assert client.get("/api/v1/reservations/tables", headers=nv).status_code == 403
    assert client.get(f"/api/v1/reservations/{res['id']}", headers=nv).status_code == 403
    assert client.post(f"/api/v1/reservations/{res['id']}/check-in", headers=nv).status_code == 403
    assert client.post(f"/api/v1/reservations/{res['id']}/no-show", headers=nv).status_code == 403
    assert client.post(f"/api/v1/reservations/{res['id']}/complete", headers=nv).status_code == 403
    assert (
        client.post(
            f"/api/v1/reservations/{res['id']}/cancel",
            json={"reason": "probe"},
            headers=nv,
        ).status_code
        == 403
    )
    assert client.get("/api/v1/reservations-metrics", headers=nv).status_code == 403

    # Nhưng thông báo ca trực vẫn mở: người trực có thể là nhân viên.
    assert client.get("/api/v1/reservations/notifications/me", headers=nv).status_code == 200

    # Quản lý vẫn làm được đầy đủ.
    assert client.get("/api/v1/reservations", headers=ql).status_code == 200
    assert client.get(f"/api/v1/reservations/{res['id']}", headers=ql).status_code == 200

    # Sửa trạng thái phải ghi `actor` là nv_id thật, không phải chuỗi role.
    assert client.post(f"/api/v1/reservations/{res['id']}/check-in", headers=ql).status_code == 200
    with _conn() as cx:
        cx.row_factory = sqlite3.Row
        row = cx.execute(
            "SELECT thuc_hien_boi FROM dat_ban_lich_su WHERE dat_ban_id=? AND trang_thai_moi='seated'",
            (res["id"],),
        ).fetchone()
    assert row is not None
    assert row["thuc_hien_boi"] == "nv_01"


# ── 11. Regression: hold hết hạn phải so bằng datetime, không so chuỗi ───────


def test_hold_con_hieu_luc_khong_bi_coi_la_het_han():
    """Hold vừa tạo (còn hiệu lực) phải giữ bàn của mình.

    `created_at` tồn tại ở hai định dạng: `...Z` (UTC) và `+07:00`. So sánh chuỗi
    giữa hai định dạng này lệch 7 tiếng nên hold vừa tạo bị coi là hết hạn ngay,
    và đơn sau chiếm lại đúng bàn đó.
    """
    giu_ban = atomic_hold_or_book_table(
        psid="psid_hold_giu",
        customer_name="Khách Giữ",
        phone="0900333444",
        booking_time="2026-09-24T19:00:00",
        party_size=4,
        status="held",
    )
    ban_bi_giu = set(giu_ban["table_ids"])
    assert ban_bi_giu, "hold phải được gán bàn"

    # Ghi `created_at` theo định dạng UTC `...Z` như `reservation_create` vẫn làm.
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as cx:
        cx.execute("UPDATE dat_ban SET created_at=? WHERE id=?", (now_utc, giu_ban["id"]))

    don_moi = atomic_hold_or_book_table(
        psid="psid_hold_moi",
        customer_name="Khách Mới",
        phone="0900555666",
        booking_time="2026-09-24T19:00:00",
        party_size=4,
    )
    # Bàn của hold còn hiệu lực KHÔNG được cấp lại.
    assert not (set(don_moi["table_ids"]) & ban_bi_giu)

    reservation_update_status(giu_ban["id"], new_status="cancelled", reason="cleanup")


def test_hold_qua_5_phut_duoc_giai_phong():
    """Hold cũ hơn 5 phút phải được nhường bàn — mặt còn lại của cùng logic."""
    from ca_api.persist import kv_set

    giu_ban = atomic_hold_or_book_table(
        psid="psid_hold_cu",
        customer_name="Khách Giữ Cũ",
        phone="0900777888",
        booking_time="2026-09-25T19:00:00",
        party_size=4,
        status="held",
    )
    ban_bi_giu = set(giu_ban["table_ids"])

    # Lùi `created_at` 30 phút theo định dạng `+07:00` (mặt định dạng còn lại).
    cu = format_ict_iso(datetime.now(ICT) - timedelta(minutes=30))
    with _conn() as cx:
        cx.execute("UPDATE dat_ban SET created_at=? WHERE id=?", (cu, giu_ban["id"]))

    # Hết hạn nên bàn được nhường: đơn mới phải lấy lại được bàn đó.
    don_moi = atomic_hold_or_book_table(
        psid="psid_hold_sau",
        customer_name="Khách Sau",
        phone="0900999000",
        booking_time="2026-09-25T19:00:00",
        party_size=4,
    )
    assert set(don_moi["table_ids"]) & ban_bi_giu, "hold quá hạn phải nhường bàn"

    reservation_update_status(giu_ban["id"], new_status="cancelled", reason="cleanup")
    kv_set("phan_cong", {})


# ── 12. Regression: khoá ghi độc quyền trên Postgres ────────────────────────


def test_acquire_write_lock_la_noop_tren_sqlite():
    """SQLite đã có `BEGIN IMMEDIATE` → hàm khoá không được gửi SQL thừa.

    `pg_advisory_xact_lock` không tồn tại trên SQLite, nên nếu hàm chạy nhầm
    ở đây thì mọi lệnh đặt bàn sẽ vỡ.
    """
    from ca_api.persist import acquire_write_lock

    with _conn() as cx:
        cx.execute("BEGIN IMMEDIATE")
        acquire_write_lock(cx, "dat_ban")
        # Nếu đã gửi `pg_advisory_xact_lock`, câu lệnh dưới đây sẽ lỗi.
        row = cx.execute("SELECT 1").fetchone()
        assert row[0] == 1


def test_acquire_write_lock_dung_khoa_tu_van_tren_postgres(monkeypatch):
    """Trên Postgres phải gửi `pg_advisory_xact_lock` với khoá băm từ scope.

    Khoá phải TẤT ĐỊNH theo scope: hai request cùng scope nhận cùng lock_id,
    khác scope nhận khoá khác (không chặn chéo bảng khác).
    """
    from ca_api import persist as persist_mod

    sent: list[tuple[str, Any]] = []

    class _GiaCursor:
        def fetchone(self) -> tuple[int]:
            return (1,)

    class _GiaConn:
        def execute(self, sql: str, params: Any = None) -> _GiaCursor:
            sent.append((sql, params))
            return _GiaCursor()

    monkeypatch.setattr(persist_mod, "_database_url", lambda: "postgresql+psycopg://x/y")
    persist_mod.acquire_write_lock(_GiaConn(), "dat_ban")

    assert len(sent) == 1
    sql, params = sent[0]
    assert "pg_advisory_xact_lock" in sql
    lock_id = params[0]

    # Tất định: cùng scope → cùng khoá.
    sent.clear()
    persist_mod.acquire_write_lock(_GiaConn(), "dat_ban")
    assert sent[0][1][0] == lock_id

    # Khác scope → khoá khác (không chặn chéo).
    sent.clear()
    persist_mod.acquire_write_lock(_GiaConn(), "kv")
    assert sent[0][1][0] != lock_id


# ── 13. Regression: tạo đơn thủ công + leo thang dự phòng ───────────────────


def test_tao_don_thu_cong_qua_api():
    """Quản lý tạo được đơn tại quầy; đơn phải đi qua khoá chống trùng bàn.

    Trước đây chỉ AI tạo được đơn — khách gọi điện thì quản lý không có cách
    nào nhập vào hệ thống, đơn tồn tại ngoài sổ và dễ trùng bàn.
    """
    from ca_api.interfaces.http.main import app as fastapi_app
    from fastapi.testclient import TestClient

    from unit.auth_util import headers

    client = TestClient(fastapi_app)
    ql = headers(client, "lan")

    # Giờ đặt phải ở tương lai (VN) — cứng "hôm nay 19:00" đỏ khi CI chạy sau 19h.
    vn = timezone(timedelta(hours=7))
    booking = (datetime.now(vn) + timedelta(days=1)).replace(
        hour=19, minute=0, second=0, microsecond=0
    )
    booking_iso = booking.strftime("%Y-%m-%dT%H:%M:%S")

    res = client.post(
        "/api/v1/reservations",
        json={
            "customer_name": "Khách Quầy",
            "phone": "0900444555",
            "booking_time": booking_iso,
            "party_size": 2,
        },
        headers=ql,
    )
    assert res.status_code == 200, res.text
    data = res.json()["reservation"]
    assert data["customer_name"] == "Khách Quầy"
    assert data["source"] == "staff_manual"
    assert data["table_ids"], "phải được gán bàn"

    # Nhân viên không được tạo đơn (dữ liệu khách).
    nv = headers(client, "minh")
    bi_chan = client.post(
        "/api/v1/reservations",
        json={
            "customer_name": "X",
            "phone": "0900000000",
            "booking_time": booking_iso,
            "party_size": 2,
        },
        headers=nv,
    )
    assert bi_chan.status_code == 403

    # Dữ liệu sai → 422, không phải 500.
    xau = client.post(
        "/api/v1/reservations",
        json={"customer_name": "", "phone": "", "booking_time": "", "party_size": 2},
        headers=ql,
    )
    assert xau.status_code == 422


def test_leo_thang_cho_nguoi_du_phong_khi_truong_ca_chua_xac_nhan():
    """`backup_nv_ids` phải được DÙNG: nhắc người dự phòng khi trưởng ca im lặng.

    Trước đây danh sách dự phòng được tính công phu nhưng không nơi nào đọc —
    trưởng ca bận thì không ai được nhắc.
    """
    from ca_api.persist import kv_set, thong_bao_ca_list

    # T6 tối (w1_c47..c50): nv_05 là nhân viên (trưởng ca), nv_02 là chủ quán (dự phòng).
    kv_set("phan_cong", {"w1_c47": ["nv_05"], "w1_c48": ["nv_02"]})
    try:
        res = atomic_hold_or_book_table(
            psid="psid_escalate",
            customer_name="Khách Chờ",
            phone="0900666777",
            booking_time="2026-10-02T19:00:00",
            party_size=4,
        )
        # Trưởng ca được chọn theo quy tắc ưu tiên (chủ quán > nhân viên).
        with _conn() as cx:
            cx.row_factory = sqlite3.Row
            row = cx.execute(
                "SELECT notified_nv_id, created_at FROM dat_ban WHERE id=?", (res["id"],)
            ).fetchone()
        truong_ca = row["notified_nv_id"]
        assert truong_ca, "phải có trưởng ca nhận thông báo"

        # Lùi created_at để vượt ngưỡng leo thang, và để notification_acked_at NULL.
        cu = format_ict_iso(datetime.now(ICT) - timedelta(minutes=30))
        with _conn() as cx:
            cx.execute(
                "UPDATE dat_ban SET created_at=?, notification_acked_at=NULL WHERE id=?",
                (cu, res["id"]),
            )

        ket_qua = notify_backup_if_unacked()
        assert ket_qua["count"] >= 1, "phải nhắc ít nhất một người dự phòng"

        # Người dự phòng nhận được thông báo cho đúng đơn này.
        da_nhac = [x for x in ket_qua["escalated"] if x.startswith(res["id"] + ":")]
        assert da_nhac, "thông báo leo thang phải trỏ đúng đơn"
        nv_du_phong = da_nhac[0].split(":", 1)[1]
        assert nv_du_phong != truong_ca, "không nhắc lại chính trưởng ca"
        assert thong_bao_ca_list(nv_id=nv_du_phong), "người dự phòng phải có thông báo"

        # Idempotent: chạy lại không tạo thêm.
        lan_hai = notify_backup_if_unacked()
        assert not [x for x in lan_hai["escalated"] if x.startswith(res["id"] + ":")]
    finally:
        kv_set("phan_cong", {})


def test_khong_leo_thang_khi_truong_ca_da_xac_nhan():
    """Đã xác nhận thì không nhắc dự phòng — tránh nhiễu."""
    from ca_api.persist import kv_set

    kv_set("phan_cong", {"w1_c47": ["nv_05"], "w1_c48": ["nv_02"]})
    try:
        res = atomic_hold_or_book_table(
            psid="psid_da_ack",
            customer_name="Khách Đã Xác Nhận",
            phone="0900888999",
            booking_time="2026-10-03T19:00:00",
            party_size=2,
        )
        cu = format_ict_iso(datetime.now(ICT) - timedelta(minutes=30))
        with _conn() as cx:
            cx.execute(
                "UPDATE dat_ban SET created_at=?, notification_acked_at=? WHERE id=?",
                (cu, format_ict_iso(datetime.now(ICT)), res["id"]),
            )
        ket_qua = notify_backup_if_unacked()
        assert not [x for x in ket_qua["escalated"] if x.startswith(res["id"] + ":")]
    finally:
        kv_set("phan_cong", {})


def test_dispatch_in_background_khong_chan_luong_goi():
    """Gửi thông báo nền: hàm trả về NGAY, không chờ Telegram.

    Telegram chậm không được làm treo lượt trả lời khách.
    """
    import time

    from ca_api.services import table_reservation_service as svc

    goi: list[dict[str, Any]] = []

    def _gia_cham(reservation: dict[str, Any], store_id: str = "quan_01") -> None:
        time.sleep(1.5)  # mô phỏng Telegram chậm
        goi.append(reservation)

    goc = svc.dispatch_reservation_notification
    svc.dispatch_reservation_notification = _gia_cham  # type: ignore[assignment]
    try:
        bat_dau = time.monotonic()
        svc.dispatch_in_background({"id": "res_bg", "customer_name": "X"})
        thoi_gian = time.monotonic() - bat_dau
        assert thoi_gian < 0.5, f"phải trả về ngay, nhưng mất {thoi_gian:.2f}s"
    finally:
        svc.dispatch_reservation_notification = goc  # type: ignore[assignment]


