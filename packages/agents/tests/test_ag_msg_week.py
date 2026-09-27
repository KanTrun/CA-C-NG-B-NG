# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Test AG-MSG suy luận TUẦN — chống bug "mọi tuần thành W01/W02".

Bug QA đợt 4 (2026-09-26): `POST /api/v1/msg/classify` gọi `classify(text)` mà
KHÔNG truyền `base_iso_week`, nên hàm mặc định "2026-W01" → "tuần sau" luôn ra
"2026-W02" và "tuần này" ra "2026-W01", bất kể hôm nay là tuần nào. Hệ quả:
ràng buộc nghỉ/đổi ca bị ghi vào tuần SAI.

Test này khoá hành vi đúng:
1. `base_iso_week` phải được tôn trọng.
2. Tràn năm phải xử lý (W52/W53 → năm sau W01).
"""

from __future__ import annotations

from ca_agents.ag_msg.extract import _extract_tuan, classify


def test_tuan_sau_tinh_tu_base() -> None:
    """'tuần sau' phải cộng 1 từ base thật, không phải từ W01."""
    assert _extract_tuan("tuần sau em nghỉ", "2026-W39") == "2026-W40"
    assert _extract_tuan("tuần sau em nghỉ", "2026-W01") == "2026-W02"


def test_tuan_nay_tinh_tu_base() -> None:
    assert _extract_tuan("tuần này em bận", "2026-W39") == "2026-W39"


def test_khong_chi_dinh_tuan_tra_ve_base() -> None:
    assert _extract_tuan("mai em nghỉ", "2026-W39") == "2026-W39"


def test_tran_nam_w52_52_tuan() -> None:
    """W52 của năm có 52 tuần → tuần sau là NĂM SAU W01, không phải W53."""
    result = _extract_tuan("tuần sau nghỉ", "2026-W52")
    assert result in {"2026-W53", "2027-W01"}, result
    # 2026 có 53 tuần ISO → W53 hợp lệ; kiểm năm có 52 tuần
    result_52 = _extract_tuan("tuần sau nghỉ", "2025-W52")
    assert result_52 == "2026-W01", f"2025 có 52 tuần ISO, phải sang 2026-W01, được {result_52}"


def test_tuan_ghi_ro_trong_cau() -> None:
    """Người dùng ghi rõ 'W40' thì phải lấy đúng năm của base."""
    assert _extract_tuan("nghỉ W40", "2026-W39") == "2026-W40"
    assert _extract_tuan("nghỉ 2026-W40", "2026-W39") == "2026-W40"


def test_classify_nhan_base_iso_week() -> None:
    """classify() phải trả tuan_id theo base được truyền."""
    r = classify("Tuần sau em xin nghỉ thứ 6", base_iso_week="2026-W39")
    assert r.rang_buoc.get("tuan_id") == "2026-W40", r.rang_buoc
    # Câu có từ khoá tier-1 khác, cùng base → vẫn đúng tuần
    r2 = classify("Tuần sau em muốn đổi ca tối", base_iso_week="2026-W39")
    assert r2.rang_buoc.get("tuan_id") == "2026-W40", r2.rang_buoc


def test_classify_khong_base_van_dung_mac_dinh_cu() -> None:
    """Không truyền base → giữ mặc định W01 (không phá test cũ / replay CI)."""
    r = classify("Tuần sau em xin nghỉ thứ 6")
    assert r.rang_buoc.get("tuan_id") == "2026-W02"
