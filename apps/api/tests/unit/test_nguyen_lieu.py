"""Test bảng nguyên liệu chuẩn — nguồn duy nhất cho mã/tên/đơn vị/nhóm.

Bảo hai thứ mà test khác không thấy:
1. Hàm chuẩn hoá đọc được DỮ LIỆU CŨ đang nằm trong DB (mã legacy, tên mất dấu,
   dòng seeder sai hình dạng) — nếu hỏng thì `/tieu-thu` lại hiện ô trống và
   trùng mặt hàng như trước.
2. Bảng bí danh đây không lệch với `ca_agents.ag_waste.loss.BI_DANH` — hai bảng
   cùng nói "cafe_g là cà phê hạt" mà mỗi nơi một kiểu thì hao hụt và sổ tiêu
   thụ sẽ join ra hai kết quả khác nhau.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT / "apps" / "api" / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from ca_api.nguyen_lieu import (  # noqa: E402
    ALIAS,
    DANH_MUC,
    TEN_BI_DANH,
    TRUONG_TOI_THIEU,
    bang_nguyen_lieu,
    chuan_hoa_bom,
    chuan_hoa_dong_tieu_thu,
    chuan_hoa_ma,
    chi_muc_mon_theo_nguyen_lieu,
    don_vi,
    la_ma_chuan,
    loc_dong_tieu_thu,
    nhom_nguyen_lieu,
    ten_nguyen_lieu,
    tim_ma_theo_ten,
    tong_hop_tieu_thu,
)


# ── Bảng chuẩn ────────────────────────────────────────────────────────────────


def test_doc_duoc_du_15_nguyen_lieu() -> None:
    bang = bang_nguyen_lieu()
    assert len(bang) >= 15
    assert bang["ca_phe_hat"] == {"ten": "Cà phê hạt", "don_vi": "g", "nhom": "ca_phe"}
    assert bang["ly"]["nhom"] == "ca_phe"
    assert bang["nuoc_dong_chai"]["nhom"] == "nuoc_dong_chai"


def test_duong_dan_file_danh_muc_dung() -> None:
    assert DANH_MUC.exists(), DANH_MUC
    assert json.loads(DANH_MUC.read_text(encoding="utf-8"))["nguyen_lieu"]


def test_ten_co_dau_va_don_vi_dung() -> None:
    assert ten_nguyen_lieu("ca_phe_hat") == "Cà phê hạt"
    assert ten_nguyen_lieu("sua_dac") == "Sữa đặc"
    assert don_vi("ca_phe_hat") == "g"
    assert don_vi("sua_tuoi") == "ml"
    assert don_vi("ly") == "cái"
    assert nhom_nguyen_lieu("tra") == "tra"


def test_ma_la_khong_bia_ten_khong_co() -> None:
    # Mã lạ không có trong bảng → humanise, không bịa tiếng Việt.
    assert ten_nguyen_lieu("sua_dac_nha") == "sua dac nha"
    assert don_vi("sua_dac_nha") == "đơn vị"
    assert nhom_nguyen_lieu("sua_dac_nha") == ""
    assert la_ma_chuan("sua_dac_nha") is False
    assert la_ma_chuan("ca_phe_hat") is True


# ── Quy mã ────────────────────────────────────────────────────────────────────


def test_ma_legacy_ve_ma_chuan() -> None:
    assert chuan_hoa_ma("cafe_g") == "ca_phe_hat"
    assert chuan_hoa_ma("sua_ml") == "sua_tuoi"
    assert chuan_hoa_ma("dao_lat") == "dao"
    assert chuan_hoa_ma("ca_phe_hat") == "ca_phe_hat"
    # Mã lạ giữ nguyên — xoá nó là xoá mất dòng sổ người ta vừa ghi.
    assert chuan_hoa_ma("sua_dac_nha") == "sua_dac_nha"


def test_tim_ma_theo_ten_mat_dau() -> None:
    assert tim_ma_theo_ten("Ca phe hat") == "ca_phe_hat"
    assert tim_ma_theo_ten("Cà phê hạt") == "ca_phe_hat"
    assert tim_ma_theo_ten("Sua tuoi") == "sua_tuoi"
    assert tim_ma_theo_ten("  DUONG  ") == "duong"
    assert tim_ma_theo_ten("Sữa đặc nhà") is None
    assert tim_ma_theo_ten("") is None


def test_tim_ma_theo_ten_dung_bi_danh() -> None:
    # Tên seeder cũ gõ tay: không khớp tên chuẩn, phải qua TEN_BI_DANH.
    assert tim_ma_theo_ten("Ly giay") == "ly"
    assert tim_ma_theo_ten("Tra da") == "tra"
    assert tim_ma_theo_ten("ca phe") == "ca_phe_hat"


def test_bi_danh_muc_tieu_co_trong_bang() -> None:
    # Alias không được trỏ vào mã không tồn tại — nếu không thì "đã chuẩn hoá"
    # lại thành mã lạ và tách mặt hàng ra lần nữa.
    for k, v in {**ALIAS, **TEN_BI_DANH}.items():
        assert la_ma_chuan(v), f"{k} -> {v} không có trong bảng chuẩn"


def test_bi_danh_dong_nhat_voi_loss_cua_hao_hut() -> None:
    from ca_agents.ag_waste.loss import BI_DANH

    # Mọi mã đích của bảng hao hụt phải là mã chuẩn ở đây, nếu không hai bảng
    # join hai kết quả khác nhau (hao hụt một đằng, sổ tiêu thụ một đằng).
    # So MÃ chứ không so tên: `loss` là nhãn hiển thị riêng của màn hao hụt.
    for k, v in BI_DANH.items():
        assert la_ma_chuan(v), f"loss.BI_DANH[{k}] = {v} không có ở nguyen_lieu"


# ── BOM ───────────────────────────────────────────────────────────────────────


def test_chuan_hoa_bom_ve_ma_chuan() -> None:
    assert chuan_hoa_bom({"cafe_g": 16, "sua_ml": 40, "ly": 1}) == {
        "ca_phe_hat": 16,
        "sua_tuoi": 40,
        "ly": 1,
    }


def test_chuan_hoa_bom_cong_dinh_muc_khi_trung_ma() -> None:
    assert chuan_hoa_bom({"cafe_g": 16, "ca_phe_hat": 4}) == {"ca_phe_hat": 20}


def test_chuan_hoa_bom_bo_dong_hong_va_am() -> None:
    assert chuan_hoa_bom({"ca_phe_hat": "abc", "ly": -2, "duong": 0}) == {}
    assert chuan_hoa_bom("khong phai dict") == {}


def test_chuan_hoa_bom_giu_so_nguyen() -> None:
    # JSON phải ghi `18`, không `18.0` — người đọc thấy lẻ thừa là nghi lỗi.
    bom = chuan_hoa_bom({"ca_phe_hat": 18.0, "sua_dac": 20})
    assert json.loads(json.dumps(bom)) == {"ca_phe_hat": 18, "sua_dac": 20}


# ── Sổ tiêu thụ ───────────────────────────────────────────────────────────────


def test_dong_legacy_bi_bo_khong_phai_render_o_trong() -> None:
    row = {"order_id": "fx_don_003", "status": "posted", "items": {"ca_phe_hat": 18}}
    assert chuan_hoa_dong_tieu_thu(row) is None
    assert chuan_hoa_dong_tieu_thu("chu khong phai dict") is None
    assert chuan_hoa_dong_tieu_thu({"hang": "duong"}) is None, "thiếu so_luong"
    assert chuan_hoa_dong_tieu_thu({"hang": "", "so_luong": 1}) is None
    assert set(TRUONG_TOI_THIEU) == {"hang", "so_luong"}


def test_dong_sach_tra_ten_co_dau_va_don_vi() -> None:
    row = chuan_hoa_dong_tieu_thu(
        {"id": "a", "hang": "Ca phe hat", "so_luong": 24, "don_vi": "g"}
    )
    assert row is not None
    assert row["ma"] == "ca_phe_hat"
    assert row["hang"] == "Cà phê hạt"
    assert row["hang_goc"] == "Ca phe hat"
    assert row["don_vi"] == "g"
    assert row["nhom"] == "ca_phe"


def test_dong_ma_legacy_duoc_quy_ve_ma_chuan() -> None:
    row = chuan_hoa_dong_tieu_thu({"id": "a", "hang": "cafe_g", "so_luong": 18})
    assert row is not None
    assert row["ma"] == "ca_phe_hat"
    assert row["hang"] == "Cà phê hạt"
    assert row["don_vi"] == "g"


def test_ten_tu_do_giu_nguyen_dung_chu_chu_quan_goi() -> None:
    row = chuan_hoa_dong_tieu_thu({"id": "a", "hang": "Sữa đặc nhà", "so_luong": 5})
    assert row is not None
    assert row["hang"] == "Sữa đặc nhà"
    assert row["nhom"] == ""


def test_so_luong_khong_doc_duoc_bi_bo() -> None:
    assert chuan_hoa_dong_tieu_thu({"hang": "duong", "so_luong": "abc"}) is None


def test_khong_gop_khi_thoi_gian_thieu() -> None:
    # Không có `luc` thì không biết hai dòng có cùng lúc không — gộp là xoá mất
    # một lần kiểm kê thật, và mất âm thầm.
    sach, bo = loc_dong_tieu_thu(
        [
            {"id": "1", "hang": "ly", "so_luong": 2},
            {"id": "2", "hang": "ly", "so_luong": 2},
        ]
    )
    assert len(sach) == 2
    assert bo == 0


def test_gop_dung_dong_trung_co_thoi_gian() -> None:
    sach, bo = loc_dong_tieu_thu(
        [
            {"id": "1", "hang": "Ca phe hat", "so_luong": 4, "luc": "T1", "nguon": "x"},
            {"id": "2", "hang": "Ca phe hat", "so_luong": 4, "luc": "T1", "nguon": "x"},
            {"id": "3", "hang": "Ca phe hat", "so_luong": 4, "luc": "T2", "nguon": "x"},
        ]
    )
    assert len(sach) == 2
    assert bo == 1


def test_loc_bo_dong_hong_va_bao_so_luong() -> None:
    sach, bo = loc_dong_tieu_thu(
        [
            {"order_id": "x", "items": {}},
            "khong phai dict",
            {"id": "1", "hang": "ly", "so_luong": 2},
        ]
    )
    assert len(sach) == 1
    assert bo == 2


# ── Gộp theo nguyên liệu ──────────────────────────────────────────────────────


def test_chi_muc_mon_bo_mon_dang_an() -> None:
    menu = [
        {"id": "ca_phe_den", "ten": "Cà phê đen", "nhom": "ca_phe", "bom": {"ca_phe_hat": 18}},
        {"id": "goi_250", "ten": "Gói 250g", "nhom": "nguyen_lieu", "an": 1, "bom": {"ca_phe_hat": 250}},
        {"id": "tra_dao", "ten": "Trà đào", "nhom": "tra", "bom": {"cafe_g": 1, "tra": 8}},
    ]
    chi_muc = chi_muc_mon_theo_nguyen_lieu(menu)

    assert [m["id"] for m in chi_muc["ca_phe_hat"]] == ["ca_phe_den", "tra_dao"]
    assert [m["id"] for m in chi_muc["tra"]] == ["tra_dao"]


def test_tong_hop_gop_theo_nguyen_lieu_va_noi_voi_mon() -> None:
    menu = [
        {"id": "ca_phe_den", "ten": "Cà phê đen", "nhom": "ca_phe", "bom": {"ca_phe_hat": 18}},
        {"id": "ca_phe_sua", "ten": "Cà phê sữa", "nhom": "ca_phe", "bom": {"ca_phe_hat": 16}},
        {"id": "goi_250", "ten": "Gói 250g", "nhom": "nguyen_lieu", "an": 1, "bom": {"ca_phe_hat": 250}},
    ]
    sach, _ = loc_dong_tieu_thu(
        [
            {"id": "1", "hang": "cafe_g", "so_luong": 18, "luc": "T1", "mon_id": "ca_phe_den"},
            {"id": "2", "hang": "Ca phe hat", "so_luong": 24, "luc": "T2", "mon_id": "ca_phe_den"},
            {"id": "3", "hang": "Ly giay", "so_luong": 12, "luc": "T1"},
        ]
    )

    tong = tong_hop_tieu_thu(sach, menu)
    assert [d["ma"] for d in tong] == ["ca_phe_hat", "ly"]
    coffee = tong[0]
    assert coffee["hang"] == "Cà phê hạt"
    assert coffee["don_vi"] == "g"
    assert coffee["nhom"] == "ca_phe"
    assert coffee["so_luong"] == 42
    assert coffee["so_dong"] == 2
    assert coffee["moi_nhat"] == "T2"
    # Món đang bán nối vào — kể cả dòng đếm tay không có `mon_id`.
    assert [m["id"] for m in coffee["mon_lien_quan"]] == ["ca_phe_den", "ca_phe_sua"]
    assert coffee["so_mon"] == 2
    # Món bao bì đang ẩn không tính là món "hiện tại".
    assert "goi_250" not in [m["id"] for m in coffee["mon_lien_quan"]]
    # Dòng đếm tay vẫn hiện tên đúng và được gộp vào đúng nhóm.
    assert tong[1]["ma"] == "ly"
    assert tong[1]["nhom"] == "ca_phe"


def test_tong_hop_ten_tu_do_muon_nhom_tu_mon_gay_ra() -> None:
    menu = [{"id": "ca_phe_sua", "ten": "Cà phê sữa", "nhom": "ca_phe", "bom": {"sua_dac": 20}}]
    sach, _ = loc_dong_tieu_thu(
        [{"id": "1", "hang": "Sữa đặc nhà", "so_luong": 5, "mon_id": "ca_phe_sua"}]
    )

    tong = tong_hop_tieu_thu(sach, menu)

    assert len(tong) == 1
    assert tong[0]["hang"] == "Sữa đặc nhà"
    assert tong[0]["nhom"] == "ca_phe", "mượn nhóm của món gây ra dòng, để vẫn lọc được"
    # Không đoán từ "món nào dùng nguyên liệu này" — một nguyên liệu đi vào nhiều
    # nhóm món, đoán là đặt nó vào sai chip lọc.
    assert tong[0]["mon_lien_quan"] == []


def test_tong_hop_ten_tu_do_khong_co_mon_id_de_nhom_trong() -> None:
    menu = [{"id": "ca_phe_sua", "ten": "Cà phê sữa", "nhom": "ca_phe", "bom": {"sua_dac": 20}}]
    sach, _ = loc_dong_tieu_thu([{"id": "1", "hang": "Sữa đặc nhà", "so_luong": 5}])

    tong = tong_hop_tieu_thu(sach, menu)

    assert len(tong) == 1
    assert tong[0]["nhom"] == "", "không biết món nào gây ra thì để trống, không bịa"


def test_tong_hop_bo_dong_am_va_khong_do_so() -> None:
    assert tong_hop_tieu_thu(None) == []
    assert tong_hop_tieu_thu([{"hang": "duong", "so_luong": -3}]) == []
    assert tong_hop_tieu_thu([{"hang": "duong", "so_luong": "abc"}]) == []
