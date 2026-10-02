# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Tests for AG-SOP ops context and topic guards."""

from __future__ import annotations

from typing import Any, cast

from ca_agents.ag_sop import answer
from ca_agents.ag_sop.ops import SopOpsContext, filter_luat_for_sop, topic_blocked


def test_topic_blocked_may_lanh_vs_tu_lanh() -> None:
    assert topic_blocked("Nhiệt độ máy lạnh bao nhiêu?", "Ghi nhiệt độ tủ lạnh")
    assert not topic_blocked("Nhiệt độ tủ lạnh bao nhiêu?", "Ghi nhiệt độ tủ lạnh")


def test_filter_luat_by_ops_context() -> None:
    laws = [
        {
            "id": "luat_t7",
            "trang_thai": "hieu_luc",
            "cau": "T7 chiều 3 pha chế",
            "dieu_kien": {"thu": "T7", "khung": "chieu"},
        },
        {
            "id": "luat_chung",
            "trang_thai": "hieu_luc",
            "cau": "Rửa tay trước khi pha chế",
        },
    ]
    t2 = SopOpsContext(ngay="2026-08-31", thu="T2", khung="sang")
    scoped = filter_luat_for_sop(cast(list[dict[str, Any]], laws), t2)
    assert len(scoped) == 1
    assert scoped[0]["id"] == "luat_chung"


def test_may_lanh_question_returns_chua_co() -> None:
    buoc = [
        {
            "ma": "nhiet_do_tu_lanh",
            "ten": "Ghi nhiệt độ tủ lạnh",
            "phieu_ten": "Mở quán",
            "nguong": {"min": 2, "max": 8},
        }
    ]
    res = answer("Nhiệt độ máy lạnh bao nhiêu là được?", buoc=buoc, luat=[])
    assert res.chua_co is True
    assert "máy lạnh" in res.cau_tra_loi.lower() or "điều hòa" in res.cau_tra_loi.lower()


def test_conditional_law_theo_context_hoac_hint_cau_hoi() -> None:
    """Luật có điều kiện thời gian: khớp ca hiện tại, HOẶC câu hỏi nêu đích danh."""
    luat = [
        {
            "id": "luat_pin",
            "trang_thai": "hieu_luc",
            "cau": "Thứ Bảy ca chiều cần 3 người pha chế, không phải 2",
            "dieu_kien": {"thu": "T7", "khung": "chieu", "vi_tri": "pha_che", "so_nguoi": 3},
        }
    ]
    wrong = SopOpsContext(ngay="2026-08-31", thu="T2", khung="sang")

    # Câu hỏi nêu đích danh "Thứ Bảy ca chiều" → trả lời, dù ca hiện tại T2 sáng.
    res_hint = answer(
        "Thứ Bảy ca chiều cần mấy người pha chế?",
        buoc=[],
        luat=luat,
        ops_context=wrong,
    )
    assert not res_hint.chua_co
    assert "luat:luat_pin" in res_hint.trich_dan

    # Câu hỏi không nêu thứ → không đoán, vẫn theo ngữ cảnh ca hiện tại.
    res_thieu = answer(
        "Ca chiều cần mấy người pha chế?",
        buoc=[],
        luat=luat,
        ops_context=wrong,
    )
    assert res_thieu.chua_co is True

    # Ngữ cảnh đúng → trả lời như cũ.
    right = SopOpsContext(ngay="2026-08-30", thu="T7", khung="chieu")
    res_right = answer(
        "Thứ Bảy ca chiều cần mấy người pha chế?",
        buoc=[],
        luat=luat,
        ops_context=right,
    )
    assert not res_right.chua_co
    assert "luat:luat_pin" in res_right.trich_dan


def test_buoc_answer_includes_viec_lam() -> None:
    buoc = [
        {
            "ma": "nhiet_do_tu_lanh",
            "ten": "Ghi nhiệt độ tủ lạnh",
            "phieu": "mo_quan",
            "phieu_ten": "Mở quán",
            "nguong": {"min": 2, "max": 8},
        }
    ]
    res = answer("Nhiệt độ tủ lạnh bao nhiêu là được?", buoc=buoc, luat=[])
    assert not res.chua_co
    assert res.viec_lam
    assert "/phieu" in res.cau_tra_loi or "/phieu" in res.viec_lam
    assert res.phieu_ma == "mo_quan"
    assert res.ngu_canh.get("thu")
