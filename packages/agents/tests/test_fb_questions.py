# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Tests cho bộ câu hỏi Fanpage + ẩn danh hóa (kế hoạch JEV v2 §4.2, §4.3, §6)."""

from __future__ import annotations

from ca_agents.sensors.fb_questions import (
    FB_QUESTIONS,
    INJECTION_QUESTIONS,
    anonymize_state,
)

# ── Bộ câu hỏi ──────────────────────────────────────────────────────────────


def test_fb_questions_have_required_fields() -> None:
    """Mọi câu hỏi đều có type + instructions (schema TypeSafe)."""
    for name, q in FB_QUESTIONS.items():
        assert "type" in q, f"{name} thiếu type"
        assert "instructions" in q, f"{name} thiếu instructions"
        assert q["type"] in ("noul", "choice", "score")


def test_fb_questions_cover_required_signals() -> None:
    """Đủ các tín hiệu bảng quyết định §4.2."""
    expected = {
        "nguy_co_suc_khoe",
        "de_doa_phap_ly_truyen_thong",
        "muc_gay_gat",
        "doi_gap_nguoi_that",
        "y_dinh",
        "co_ve_mia_mai",
    }
    assert expected <= set(FB_QUESTIONS)


def test_injection_questions() -> None:
    assert set(INJECTION_QUESTIONS) == {
        "co_gang_ghi_de_chi_dan",
        "hoi_du_lieu_noi_bo",
    }


# ── Ẩn danh hóa (§6) ────────────────────────────────────────────────────────


def test_anonymize_phone() -> None:
    text = "gọi em 0912345678 nhé"
    out = anonymize_state({"noi_dung_khach": text})
    assert "0912345678" not in out["noi_dung_khach"]
    assert "KH_SDT" in out["noi_dung_khach"]


def test_anonymize_with_name_map() -> None:
    text = "Lan ơi, mai mình nghỉ nhé"
    out = anonymize_state({"noi_dung_khach": text}, name_map={"Lan": "NV_03"})
    assert "Lan" not in out["noi_dung_khach"]
    assert "NV_03" in out["noi_dung_khach"]


def test_anonymize_nested_dict() -> None:
    state = {"tin_nhan": {"noi_dung": "sđt 0912345678"}, "khach": "123"}
    out = anonymize_state(state)
    assert "0912345678" not in out["tin_nhan"]["noi_dung"]
    assert "KH_SDT" in out["tin_nhan"]["noi_dung"]


def test_anonymize_keeps_common_words() -> None:
    """Không mask nhầm từ thường như 'Quán', 'Menu'."""
    text = "Quán Menu hôm nay có gì ngon?"
    out = anonymize_state({"noi_dung_khach": text})
    assert "quán" in out["noi_dung_khach"].lower() or "Menu" in out["noi_dung_khach"]


def test_anonymize_name_heuristic() -> None:
    """Heuristic phát hiện tên riêng Capitalized → KH_xx."""
    text = "Bạn Trâm ơi cho hỏi giờ mở cửa"
    out = anonymize_state({"noi_dung_khach": text})
    assert "Trâm" not in out["noi_dung_khach"]
    assert "KH_" in out["noi_dung_khach"]


def test_anonymize_khong_de_lot_ten_dau_cau() -> None:
    """Tên đứng ngay đầu câu vẫn phải bị mask.

    Lỗi cũ: chỉ mask chuỗi ≥ 2 từ, nên "Nam ơi …", "Hùng ạ …", "Chị Hoa …" —
    đúng những câu chào phổ biến nhất của khách — đi nguyên sang TypeSafe.
    """
    for cau in (
        "Nam ơi cho em hỏi giờ mở cửa",
        "Hùng ạ em xin nghỉ ca sáng",
        "Trâm ơi mai em bận",
        "Lan nhé mai mình nghỉ",
        "Anh Nam ơi cho em hỏi",
        "Chị Hoa cho em xin nghỉ",
        "Anh Tuấn cho em xin nghỉ",
        "Nguyễn Văn Nam gọi lúc 9h nhé",
    ):
        out = anonymize_state({"noi_dung_khach": cau})["noi_dung_khach"]
        assert "KH_" in out, f"lọt tên: {cau!r} → {out!r}"


def test_anonymize_khong_mask_nham_cau_nghiep_vu() -> None:
    """Từ viết hoa ĐẦU CÂU không phải tên thì không được mask.

    Mask nhầm làm câu hỏi gửi Jev méo nghĩa (vd "Dạ em cảm ơn" → "KH_01 em cảm
    ơn"), mà đó lại là phần lớn tin nhắn thật.
    """
    for cau in (
        "Dạ em cảm ơn chị nhiều",
        "Vâng em biết rồi ạ",
        "Quán mở cửa chưa ạ",
        "Menu hôm nay có gì",
        "Hôm nay quán đông không",
        "Thứ Hai tuần sau em nghỉ",
        "Pha Chế hôm nay vắng",
        "Đơn hàng của tôi bị sai",
        "Lịch tuần này thế nào",
        "Khách báo đau bụng",
        "Bảng lương tháng này",
        "Ca sáng nay vắng",
    ):
        out = anonymize_state({"noi_dung_khach": cau})["noi_dung_khach"]
        assert out == cau, f"mask nhầm câu nghiệp vụ: {cau!r} → {out!r}"