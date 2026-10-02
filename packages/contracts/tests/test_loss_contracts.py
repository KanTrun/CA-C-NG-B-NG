"""Hợp đồng hao hụt — validate trước khi có logic nghiệp vụ (ADR-003).

Trọng tâm: khẳng định `None` (chưa có dữ liệu) **khác** `0.0` (có dữ liệu, bằng
không). Trộn hai thứ này là bịa số; đây là ràng buộc chính của plan 260923-1736.
"""

from __future__ import annotations

import pytest
from ca_contracts import (
    LossBasis,
    LossCauseRank,
    LossCauseSource,
    LossLevel,
    LossLine,
    LossSummary,
    LossThreshold,
)
from pydantic import ValidationError


def test_enum_values_are_stable_strings() -> None:
    """Mã enum là giao kèo với API/UI — đổi là breaking, phải cố ý."""
    assert LossLevel.DAT.value == "dat"
    assert LossLevel.THIEU_DU_LIEU.value == "thieu_du_lieu"
    assert LossBasis.KE_HOACH_KIEM_KE.value == "ke_hoach_kiem_ke"
    assert LossCauseSource.NGUYEN_NHAN_GHI.value == "nguyen_nhan_ghi"


def test_level_has_missing_data_branch() -> None:
    """Fail-closed: phải có nhánh biểu diễn 'chưa biết'.

    Thiếu nhánh này thì hệ thống buộc phải chọn giữa 'đạt' và 'cảnh báo' khi không
    có số — cả hai đều là kết luận không có bằng chứng.
    """
    assert LossLevel.THIEU_DU_LIEU in set(LossLevel)


def test_none_is_not_zero() -> None:
    """`None` = chưa có dữ liệu; `0.0` = có dữ liệu và bằng không. Không được lẫn."""
    chua_do = LossLine(mat_hang="sua_tuoi", ly_thuyet=12.0, thuc_te=None)
    da_do_bang_khong = LossLine(mat_hang="sua_tuoi", ly_thuyet=0.0, thuc_te=0.0)

    assert chua_do.thuc_te is None
    assert da_do_bang_khong.thuc_te == 0.0
    assert chua_do.thuc_te != da_do_bang_khong.thuc_te


def test_default_is_missing_data_not_dat() -> None:
    """Mặc định phải là `thieu_du_lieu` — không được mặc định 'đạt'."""
    line = LossLine(mat_hang="da")
    assert line.muc_do is LossLevel.THIEU_DU_LIEU
    assert line.ly_thuyet is None
    assert line.thuc_te is None
    assert line.lech is None
    assert line.ty_le_phan_tram is None


def test_negative_delta_is_allowed() -> None:
    """Lệch âm là hợp lệ: dùng ít hơn lý thuyết (đếm dư / công thức chưa khớp)."""
    line = LossLine(
        mat_hang="tra",
        ly_thuyet=100.0,
        thuc_te=80.0,
        lech=-20.0,
        ty_le_phan_tram=-20.0,
        muc_do=LossLevel.DAT,
    )
    assert line.lech == -20.0
    assert line.ty_le_phan_tram == -20.0
    assert line.muc_do is LossLevel.DAT


def test_amounts_reject_negative() -> None:
    """Lượng lý thuyết/thực tế là đại lượng vật lý — không âm."""
    with pytest.raises(ValidationError):
        LossLine(mat_hang="sua_tuoi", ly_thuyet=-1.0)
    with pytest.raises(ValidationError):
        LossLine(mat_hang="sua_tuoi", thuc_te=-1.0)


def test_mat_hang_is_required_and_bounded() -> None:
    with pytest.raises(ValidationError):
        LossLine(mat_hang="")
    with pytest.raises(ValidationError):
        LossLine(mat_hang="x" * 65)


def test_unknown_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LossLine(mat_hang="da", muc_do="khong_ton_tai")  # type: ignore[arg-type]


def test_thieu_ve_documents_which_side_is_missing() -> None:
    """UI cần biết thiếu vế nào để nói đúng câu, không nói chung chung."""
    thieu_thuc_te = LossLine(mat_hang="sua_tuoi", ly_thuyet=12.0, thieu_ve=["thuc_te"])
    thieu_ly_thuyet = LossLine(mat_hang="banh", thuc_te=3.0, thieu_ve=["ly_thuyet"])
    du_hai_ve = LossLine(mat_hang="da", ly_thuyet=1.0, thuc_te=1.0)

    assert thieu_thuc_te.thieu_ve == ["thuc_te"]
    assert thieu_ly_thuyet.thieu_ve == ["ly_thuyet"]
    assert du_hai_ve.thieu_ve == []


def test_cause_rank_percentage_is_bounded() -> None:
    """Tỷ lệ phần trăm không vượt 100 và không âm."""
    ok = LossCauseRank(nguyen_nhan="het_han", so_lan=3, ty_le_tong=42.5)
    assert ok.ty_le_tong == 42.5

    with pytest.raises(ValidationError):
        LossCauseRank(nguyen_nhan="het_han", so_lan=3, ty_le_tong=101.0)
    with pytest.raises(ValidationError):
        LossCauseRank(nguyen_nhan="het_han", so_lan=3, ty_le_tong=-0.1)


def test_cause_rank_rejects_negative_count() -> None:
    with pytest.raises(ValidationError):
        LossCauseRank(nguyen_nhan="het_han", so_lan=-1)


def test_summary_empty_is_honest() -> None:
    """Tóm tắt rỗng: đếm bằng 0 nhưng tỷ lệ trung bình là None, không phải 0.0."""
    s = LossSummary()
    assert s.tong_dong == 0
    assert s.ty_le_trung_binh is None
    assert s.dong == []
    assert s.nguyen_nhan_hang_dau == []
    assert s.co_du_lieu_mau is False


def test_summary_round_trip_keeps_none() -> None:
    """Round-trip qua JSON không được biến `None` thành 0."""
    s = LossSummary(
        ky="tuan",
        tong_dong=2,
        so_thieu_du_lieu=1,
        dong=[
            LossLine(mat_hang="sua_tuoi", ten="Sữa tươi", don_vi="ml", ly_thuyet=1500.0, thuc_te=1700.0, lech=200.0, ty_le_phan_tram=13.33, muc_do=LossLevel.CANH_BAO),
            LossLine(mat_hang="banh", ten="Bánh", don_vi="cái", thuc_te=3.0, muc_do=LossLevel.THIEU_DU_LIEU, thieu_ve=["ly_thuyet"]),
        ],
    )
    lai = LossSummary.model_validate_json(s.model_dump_json())

    assert lai.dong[0].ly_thuyet == 1500.0
    assert lai.dong[1].ly_thuyet is None
    assert lai.dong[1].thuc_te == 3.0


def test_threshold_prefers_per_item_value() -> None:
    """Ngưỡng riêng theo mặt hàng thắng ngưỡng mặc định."""
    t = LossThreshold(mac_dinh_phan_tram=5.0, theo_mat_hang={"sua_tuoi": 3.0})
    assert t.nguong_cho("sua_tuoi") == 3.0
    assert t.nguong_cho("mat_hang_khac") == 5.0


def test_threshold_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        LossThreshold(mac_dinh_phan_tram=-1.0)
    with pytest.raises(ValidationError):
        LossThreshold(nghiem_trong_phan_tram=-1.0)


def test_line_default_threshold_matches_contract_default() -> None:
    """Ngưỡng mặc định trên dòng phải khớp ngưỡng mặc định của cấu hình."""
    assert LossLine(mat_hang="da").nguong_phan_tram == LossThreshold().mac_dinh_phan_tram
