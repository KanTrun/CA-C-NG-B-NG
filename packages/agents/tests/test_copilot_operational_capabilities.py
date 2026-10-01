# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Unit tests for newly added operational capabilities in AG-COPILOT:
- GET_WEATHER (Thời tiết & Khuyến nghị vận hành)
- GET_TODAY_OPERATIONS (Tổng quan vận hành & Dashboard hôm nay)
- GET_FAIRNESS_SUMMARY (Báo cáo công bằng giờ làm)
- GET_MY_CHECKLIST (Checklist ca & Mẫu phiếu)
- SEARCH_TRENDS (Radar xu hướng F&B)
"""

from __future__ import annotations

from typing import Any
import pytest

from ca_agents.ag_copilot import intent_parser as ip
from ca_agents.ag_copilot import tool_registry as tr
from ca_agents.ag_copilot.copilot_agent import run_copilot
from ca_contracts import (
    CopilotContext,
    CopilotIntent,
    copilot_role_can_use_intent,
)


def test_intent_parsing_new_capabilities() -> None:
    """Kiểm tra parser nhận diện chính xác các câu hỏi có dấu và không dấu."""
    # 1. GET_WEATHER
    assert ip.parse_intent("thời tiết hôm nay thế nào").intent == "GET_WEATHER"
    assert ip.parse_intent("thoi tiet hom nay the nao").intent == "GET_WEATHER"
    assert ip.parse_intent("trời có mưa không").intent == "GET_WEATHER"
    assert ip.parse_intent("troi co mua khong").intent == "GET_WEATHER"

    # 2. GET_TODAY_OPERATIONS
    assert ip.parse_intent("tình hình quán hôm nay").intent == "GET_TODAY_OPERATIONS"
    assert ip.parse_intent("tinh hinh quan hom nay").intent == "GET_TODAY_OPERATIONS"
    assert ip.parse_intent("doanh thu hôm nay").intent == "GET_TODAY_OPERATIONS"

    # 3. GET_FAIRNESS_SUMMARY
    assert ip.parse_intent("báo cáo công bằng").intent == "GET_FAIRNESS_SUMMARY"
    assert ip.parse_intent("bao cao cong bang").intent == "GET_FAIRNESS_SUMMARY"
    assert ip.parse_intent("ai làm nhiều nhất").intent == "GET_FAIRNESS_SUMMARY"

    # 4. GET_MY_CHECKLIST
    assert ip.parse_intent("checklist của tôi").intent == "GET_MY_CHECKLIST"
    assert ip.parse_intent("checklist cua toi").intent == "GET_MY_CHECKLIST"
    assert ip.parse_intent("mẫu phiếu ca").intent == "GET_MY_CHECKLIST"

    # 5. SEARCH_TRENDS
    assert ip.parse_intent("xu hướng f&b").intent == "SEARCH_TRENDS"
    assert ip.parse_intent("xu huong f&b").intent == "SEARCH_TRENDS"
    assert ip.parse_intent("món trending").intent == "SEARCH_TRENDS"
    assert ip.parse_intent("trend đồ uống").intent == "SEARCH_TRENDS"


def test_rbac_permissions_for_new_capabilities() -> None:
    """Kiểm tra ma trận quyền: cả nhân viên và quản lý đều được phép đọc các intent R0 này."""
    new_intents = [
        "GET_WEATHER",
        "GET_TODAY_OPERATIONS",
        "GET_FAIRNESS_SUMMARY",
        "GET_MY_CHECKLIST",
        "SEARCH_TRENDS",
    ]
    for intent in new_intents:
        assert copilot_role_can_use_intent("nhan_vien", intent) is True
        assert copilot_role_can_use_intent("quan_ly", intent) is True
        assert copilot_role_can_use_intent("chu_quan", intent) is True


def test_tool_get_weather_with_data() -> None:
    """Tool thời tiết trả về đầy đủ nhiệt độ, mô tả và khuyến nghị vận hành."""
    mock_weather = {
        "co_du_lieu": True,
        "hien_tai": {
            "nhiet_do": 29.5,
            "mo_ta": "Mưa rào nhẹ",
            "mua_mm": 3.2,
        },
        "anh_huong_quan": {
            "tom_tat": "Trời mưa: ca chiều khách ngồi trong nhà nhiều hơn, kiểm tra dù và mái hiên.",
            "yeu_to": ["Mưa rào", "Tăng đơn mang đi"],
        },
        "vi_tri": {"thanh_pho": "TP Hồ Chí Minh"},
        "theo_gio": [],
    }
    tr.configure_data_sources(thoi_tiet_hom_nay=lambda store_id="quan_01": mock_weather)
    try:
        res = tr.tool_get_weather()
        assert res.success is True
        assert res.intent == "GET_WEATHER"
        assert "29.5°C" in res.summary
        assert "Mưa rào nhẹ" in res.summary
        assert "Trời mưa" in res.summary
        assert res.data["co_du_lieu"] is True
    finally:
        tr.configure_data_sources()


def test_tool_get_weather_fallback() -> None:
    """Khi không có dữ liệu GPS/thời tiết, tool trả về thông điệp trung thực không bịa số."""
    tr.configure_data_sources(thoi_tiet_hom_nay=lambda store_id="quan_01": {"co_du_lieu": False, "ly_do": "Chưa có toạ độ quán."})
    try:
        res = tr.tool_get_weather()
        assert res.success is True
        assert "Chưa có toạ độ quán" in res.summary
        assert res.data["co_du_lieu"] is False
    finally:
        tr.configure_data_sources()


def test_tool_get_today_operations() -> None:
    """Tool tổng quan hôm nay trả về số lượng việc treo và cảnh báo tồn."""
    tr.configure_data_sources(
        kv_get=lambda key, default: [
            {"id": "tr_1", "noi_dung": "Lau tủ bánh", "trang_thai": "dang_cho"}
        ] if key == "treo" else (
            [{"hang": "Sữa đặc", "duoi_nguong": True}] if key == "tieu_thu" else default
        )
    )
    try:
        res = tr.tool_get_today_operations(user_role="quan_ly")
        assert res.success is True
        assert res.intent == "GET_TODAY_OPERATIONS"
        assert "1 việc treo" in res.summary
        assert "1 mặt hàng chạm ngưỡng" in res.summary
    finally:
        tr.configure_data_sources()


def test_tool_get_fairness_summary() -> None:
    """Tool công bằng trả về kết quả định hướng trang /cong-bang."""
    tr.configure_data_sources(
        kv_get=lambda key, default: {"ca_01": ["nv_01", "nv_02"]} if key == "phan_cong" else default
    )
    try:
        res_manager = tr.tool_get_fairness_summary(user_role="quan_ly")
        assert res_manager.success is True
        assert "1 ca" in res_manager.summary
        assert "/cong-bang" in res_manager.summary

        res_staff = tr.tool_get_fairness_summary(user_role="nhan_vien")
        assert res_staff.success is True
        assert "cá nhân" in res_staff.summary
    finally:
        tr.configure_data_sources()


def test_tool_get_my_checklist() -> None:
    """Tool checklist trả về danh sách mẫu phiếu được bật."""
    tr.configure_data_sources(
        load_phieu_catalog=lambda store_id="quan_01": [
            {"ma": "mo_ca", "ten": "Mở ca sáng"},
            {"ma": "dong_ca", "ten": "Đóng ca tối"},
        ]
    )
    try:
        res = tr.tool_get_my_checklist()
        assert res.success is True
        assert "Mở ca sáng" in res.summary
        assert "Đóng ca tối" in res.summary
        assert "/phieu" in res.summary
    finally:
        tr.configure_data_sources()


def test_tool_search_trends() -> None:
    """Tool xu hướng F&B trả về danh sách món hot từ cache mà không chặn mạng."""
    tr.configure_data_sources(
        trends_cached=lambda store_id="quan_01": [
            {"ten_mon": "Trà xoài kem cheese"},
            {"ten_mon": "Cà phê muối hồng"},
        ]
    )
    try:
        res = tr.tool_search_trends()
        assert res.success is True
        assert "Trà xoài kem cheese" in res.summary
        assert "Cà phê muối hồng" in res.summary
    finally:
        tr.configure_data_sources()


def test_copilot_end_to_end_weather_dispatch() -> None:
    """Kiểm tra toàn tuyến run_copilot dispatch đúng GET_WEATHER."""
    mock_weather = {
        "co_du_lieu": True,
        "hien_tai": {"nhiet_do": 32.0, "mo_ta": "Nắng ráo", "mua_mm": 0.0},
        "anh_huong_quan": {"tom_tat": "Thời tiết thuận lợi cho lượng khách ghé quán."},
    }
    tr.configure_data_sources(thoi_tiet_hom_nay=lambda store_id="quan_01": mock_weather)
    try:
        ctx = CopilotContext(
            store_id="quan_01",
            user_id="nv_test",
            user_role="nhan_vien",
            active_date="2026-10-02",
        )
        response = run_copilot("thời tiết hôm nay quán thế nào", ctx)
        assert response.intent == "GET_WEATHER"
        assert "32.0°C" in response.reply_text
        assert "Nắng ráo" in response.reply_text
    finally:
        tr.configure_data_sources()


def test_intent_parsing_extended_operations() -> None:
    """Kiểm tra parser nhận diện chính xác 4 intent mở rộng mới (có dấu & không dấu)."""
    # 1. GET_RESERVATIONS
    assert ip.parse_intent("đặt bàn hôm nay có ai không").intent == "GET_RESERVATIONS"
    assert ip.parse_intent("dat ban hom nay").intent == "GET_RESERVATIONS"
    assert ip.parse_intent("kiểm tra bàn trống").intent == "GET_RESERVATIONS"
    assert ip.parse_intent("kiem tra ban trong").intent == "GET_RESERVATIONS"
    assert ip.parse_intent("sơ đồ bàn quán").intent == "GET_RESERVATIONS"

    # 2. GET_OPEN_SHIFTS
    assert ip.parse_intent("chợ ca hôm nay").intent == "GET_OPEN_SHIFTS"
    assert ip.parse_intent("cho ca hom nay").intent == "GET_OPEN_SHIFTS"
    assert ip.parse_intent("có ca nào trống không").intent == "GET_OPEN_SHIFTS"
    assert ip.parse_intent("co ca nao trong khong").intent == "GET_OPEN_SHIFTS"
    assert ip.parse_intent("danh sách ca mở").intent == "GET_OPEN_SHIFTS"

    # 3. GET_MEETINGS
    assert ip.parse_intent("biên bản họp gần nhất").intent == "GET_MEETINGS"
    assert ip.parse_intent("bien ban hop gan nhat").intent == "GET_MEETINGS"
    assert ip.parse_intent("kết quả họp giao ban").intent == "GET_MEETINGS"
    assert ip.parse_intent("ket qua hop giao ban").intent == "GET_MEETINGS"

    # 4. GET_PREDICTIVE_INSIGHTS
    assert ip.parse_intent("gợi ý vận hành cho quán").intent == "GET_PREDICTIVE_INSIGHTS"
    assert ip.parse_intent("goi y van hanh cho quan").intent == "GET_PREDICTIVE_INSIGHTS"
    assert ip.parse_intent("đề xuất tối ưu ca").intent == "GET_PREDICTIVE_INSIGHTS"
    assert ip.parse_intent("de xuat toi uu ca").intent == "GET_PREDICTIVE_INSIGHTS"


def test_rbac_permissions_extended_operations() -> None:
    """Kiểm tra phân quyền RBAC: GET_PREDICTIVE_INSIGHTS chỉ dành cho quản lý/chủ quán."""
    # nhan_vien can read reservations, open shifts, meetings
    assert copilot_role_can_use_intent("nhan_vien", "GET_RESERVATIONS") is True
    assert copilot_role_can_use_intent("nhan_vien", "GET_OPEN_SHIFTS") is True
    assert copilot_role_can_use_intent("nhan_vien", "GET_MEETINGS") is True
    # nhan_vien cannot read predictive suggestions (fail-closed)
    assert copilot_role_can_use_intent("nhan_vien", "GET_PREDICTIVE_INSIGHTS") is False

    # quan_ly and chu_quan have full access
    for r in ("quan_ly", "chu_quan"):
        assert copilot_role_can_use_intent(r, "GET_RESERVATIONS") is True
        assert copilot_role_can_use_intent(r, "GET_OPEN_SHIFTS") is True
        assert copilot_role_can_use_intent(r, "GET_MEETINGS") is True
        assert copilot_role_can_use_intent(r, "GET_PREDICTIVE_INSIGHTS") is True


def test_tool_get_reservations() -> None:
    """Tool tra cứu đặt bàn trả về đúng số bàn trống và danh sách khách hẹn."""
    mock_tables = [
        {"id": 1, "so_ban": "B01", "dang_dung": False, "trang_thai_hoat_dong": 1},
        {"id": 2, "so_ban": "B02", "dang_dung": True, "trang_thai_hoat_dong": 1},
        {"id": 3, "so_ban": "B03", "dang_dung": False, "trang_thai_hoat_dong": 1},
    ]
    mock_res = [
        {
            "id": "res_1",
            "customer_name": "Anh Tuấn",
            "booking_time": "2026-10-02T18:30:00",
            "party_size": 4,
            "status": "confirmed",
        }
    ]
    tr.configure_data_sources(
        table_list=lambda store_id="quan_01": mock_tables,
        reservation_list=lambda store_id="quan_01": mock_res,
    )
    try:
        res = tr.tool_get_reservations()
        assert res.success is True
        assert "3 bàn" in res.summary
        assert "2 bàn đang trống" in res.summary
        assert "Anh Tuấn" in res.summary
        assert "18:30" in res.summary
        assert "/page-quan/dat-ban" in res.summary
    finally:
        tr.configure_data_sources()


def test_tool_get_open_shifts() -> None:
    """Tool tra cứu ca mở và chợ ca."""
    mock_open_shifts = [
        {"id": "os_1", "ca_id": "T2_SANG", "tuan_iso": "2026-W40", "status": "open"},
        {"id": "os_2", "ca_id": "T3_TOI", "tuan_iso": "2026-W40", "status": "open"},
    ]
    tr.configure_data_sources(open_shift_list=lambda store_id="quan_01": mock_open_shifts)
    try:
        res = tr.tool_get_open_shifts()
        assert res.success is True
        assert "2 ca đang cần người" in res.summary
        assert "T2_SANG" in res.summary
        assert "T3_TOI" in res.summary
    finally:
        tr.configure_data_sources()


def test_tool_get_meetings() -> None:
    """Tool tra cứu biên bản họp giao ban."""
    mock_meetings = [
        {
            "id": "meet_01",
            "tieu_de": "Họp giao ban đầu tháng 10",
            "ngay": "2026-10-01",
            "tom_tat": "Thống nhất quy chuẩn phục vụ mới và phân công lại ca cuối tuần.",
            "action_items": [{"task": "Kiểm tra máy pha"}, {"task": "Đổi menu mùa thu"}],
        }
    ]
    tr.configure_data_sources(meetings_list=lambda: mock_meetings)
    try:
        res = tr.tool_get_meetings()
        assert res.success is True
        assert "Họp giao ban đầu tháng 10" in res.summary
        assert "Thống nhất quy chuẩn phục vụ mới" in res.summary
        assert "2 đầu việc/quyết định" in res.summary
        assert "/cuoc-hop" in res.summary
    finally:
        tr.configure_data_sources()


def test_tool_get_predictive_insights() -> None:
    """Tool gợi ý tối ưu vận hành từ Digital Twin."""
    mock_predict = {
        "suggestions": [
            {"ten_luat": "Tăng cường 1 nhân sự ca tối Thứ 6", "mo_ta": "Dự báo khách đông"}
        ],
        "patterns": [{"ten_mau": "Mẫu phục vụ nhanh giờ cao điểm"}],
        "twin_scenarios": [{"id": "scen_1", "ten": "Mô phỏng mưa chiều"}],
    }
    tr.configure_data_sources(predict_suggestions=lambda: mock_predict)
    try:
        res = tr.tool_get_predictive_insights()
        assert res.success is True
        assert "Tăng cường 1 nhân sự ca tối Thứ 6" in res.summary
        assert "1 kịch bản mô phỏng" in res.summary
        assert "/de-xuat-thong-minh" in res.summary
    finally:
        tr.configure_data_sources()


def test_copilot_end_to_end_reservations_and_meetings() -> None:
    """End-to-end dispatch qua run_copilot cho reservations và meetings."""
    tr.configure_data_sources(
        table_list=lambda store_id="quan_01": [{"id": 1, "so_ban": "B01", "dang_dung": False, "trang_thai_hoat_dong": 1}],
        reservation_list=lambda store_id="quan_01": [],
        meetings_list=lambda: [{"id": "m1", "tieu_de": "Họp ca sáng", "ngay": "2026-10-02", "tom_tat": "Vận hành ổn định", "action_items": []}],
    )
    try:
        ctx = CopilotContext(
            store_id="quan_01",
            user_id="nv_test",
            user_role="nhan_vien",
            active_date="2026-10-02",
        )
        resp_res = run_copilot("hôm nay có bàn nào đặt không", ctx)
        assert resp_res.intent == "GET_RESERVATIONS"
        assert "Tình hình bàn & đặt chỗ" in resp_res.reply_text

        resp_meet = run_copilot("biên bản cuộc họp gần nhất", ctx)
        assert resp_meet.intent == "GET_MEETINGS"
        assert "Họp ca sáng" in resp_meet.reply_text
    finally:
        tr.configure_data_sources()

