"""Động cơ hao hụt AG-WASTE — kiểm toán tất định (plan 260923-1736).

Trọng tâm khẳng định:

1. Công thức khớp §4.3 và khớp `audit_recipe_waste.py` đã kiểm chứng trong repo.
2. `None` (chưa đo) không bao giờ bị đọc thành `0.0` (đo được, bằng không).
3. Mặt hàng chỉ có một vế ra `thieu_du_lieu`, không ra "đạt".
4. Lệch âm (dùng ít hơn lý thuyết) không bị báo động thành hao hụt.
5. Hàm thuần: không I/O, không cần fixture DB.
"""

from __future__ import annotations

from typing import Any

from ca_agents.ag_waste import (
    chuan_hoa_mat_hang,
    doc_ban_theo_mon,
    doc_bom_theo_mon,
    gom_theo_mat_hang,
    ngay_hom_nay,
    so_hao_hut,
    tinh_ly_thuyet,
    tinh_tu_kiem_ke,
    tinh_tu_nguon,
    tong_hop,
    xep_hang_nguyen_nhan,
)
from ca_contracts import LossBasis, LossCauseSource, LossLevel, LossLine, LossThreshold

# ── Chuẩn hoá tên mặt hàng ────────────────────────────────────────────────────


def test_chuan_hoa_quy_bom_ve_ma_kho() -> None:
    """Tên theo đơn vị đo ở công thức phải quy về mã mặt hàng kho."""
    assert chuan_hoa_mat_hang("cafe_g") == "ca_phe_hat"
    assert chuan_hoa_mat_hang("sua_ml") == "sua_tuoi"


def test_chuan_hoa_giu_ma_kho_nguyen_ven() -> None:
    """Mã đã đúng thì giữ nguyên — không được nuốt."""
    assert chuan_hoa_mat_hang("sua_tuoi") == "sua_tuoi"
    assert chuan_hoa_mat_hang("ca_phe_hat") == "ca_phe_hat"


def test_chuan_hoa_giu_mat_hang_la_cua_quan() -> None:
    """Nguyên liệu riêng của quán vẫn phải có dòng — không bị loại vì lạ."""
    assert chuan_hoa_mat_hang("Syrup Vải") == "syrup_vải"
    assert chuan_hoa_mat_hang("tra-sen") == "tra_sen"


def test_chuan_hoa_rong_tra_rong() -> None:
    assert chuan_hoa_mat_hang("") == ""
    assert chuan_hoa_mat_hang("   ") == ""


# ── Gộp theo mặt hàng ─────────────────────────────────────────────────────────


def test_gom_theo_mat_hang_cong_don_nhieu_dong() -> None:
    """Nhiều ca cùng mặt hàng phải gộp thành một số, không hiện trùng dòng."""
    rows = [
        {"mat_hang": "sua_tuoi", "so_luong": 2},
        {"mat_hang": "sua_tuoi", "so_luong": 3},
        {"mat_hang": "ca_phe_hat", "so_luong": 1},
    ]
    ra = gom_theo_mat_hang(rows, "so_luong")
    assert ra == {"sua_tuoi": 5.0, "ca_phe_hat": 1.0}


def test_gom_theo_mat_hang_bo_qua_so_khong_doc_duoc() -> None:
    """Số rác không được kéo cả phép tính xuống."""
    rows: list[dict[str, Any]] = [
        {"mat_hang": "sua_tuoi", "so_luong": 2},
        {"mat_hang": "sua_tuoi", "so_luong": "khong-phai-so"},
        {"mat_hang": "sua_tuoi", "so_luong": None},
        {"mat_hang": "sua_tuoi"},
    ]
    assert gom_theo_mat_hang(rows, "so_luong") == {"sua_tuoi": 2.0}


def test_gom_theo_mat_hang_bo_qua_so_am_va_khong() -> None:
    rows = [
        {"mat_hang": "da", "so_luong": 0},
        {"mat_hang": "da", "so_luong": -5},
        {"mat_hang": "da", "so_luong": 4},
    ]
    assert gom_theo_mat_hang(rows, "so_luong") == {"da": 4.0}


def test_gom_theo_mat_hang_dong_rac_khong_raise() -> None:
    assert gom_theo_mat_hang([None, "chuoi", 42], "so_luong") == {}  # type: ignore[list-item]


# ── Lý thuyết ─────────────────────────────────────────────────────────────────


def test_tinh_ly_thuyet_khop_cong_thuc() -> None:
    """lý thuyết = định mức × số phần, đúng như barista-waste-audit."""
    # 10 latte: 18g cà phê, 150ml sữa mỗi ly
    ban = {"latte": 10}
    bom = {"latte": {"cafe_g": 18, "sua_ml": 150}}
    ra = tinh_ly_thuyet(ban, bom)
    assert ra["ca_phe_hat"] == 180.0
    assert ra["sua_tuoi"] == 1500.0


def test_tinh_ly_thuyet_gop_nhieu_mon_cung_nguyen_lieu() -> None:
    """Hai món cùng dùng cà phê thì cộng chung, không tạo hai dòng."""
    ban = {"latte": 10, "espresso": 20}
    bom = {"latte": {"cafe_g": 18}, "espresso": {"cafe_g": 18}}
    assert tinh_ly_thuyet(ban, bom) == {"ca_phe_hat": 540.0}


def test_tinh_ly_thuyet_bo_mon_khong_co_cong_thuc() -> None:
    """Không có định mức thì không có gì để so — bỏ qua, không bịa số 0."""
    ban = {"mon_la": 5, "latte": 1}
    bom = {"latte": {"cafe_g": 18}}
    assert tinh_ly_thuyet(ban, bom) == {"ca_phe_hat": 18.0}


def test_tinh_ly_thuyet_rong() -> None:
    assert tinh_ly_thuyet({}, {}) == {}
    assert tinh_ly_thuyet({"latte": 0}, {"latte": {"cafe_g": 18}}) == {}


# ── Thực tế từ kiểm kê ────────────────────────────────────────────────────────


def test_tinh_tu_kiem_ke_khop_cong_thuc_43() -> None:
    """tiêu thụ = đầu ca + nhập − cuối ca − hao hụt đã ghi (§4.3)."""
    muc = [{"mat_hang": "sua_tuoi", "dau_ca": 25, "nhap_trong_ca": 8, "cuoi_ca": 26, "hao_hut_ghi": 0}]
    assert tinh_tu_kiem_ke(muc) == {"sua_tuoi": 7.0}


def test_tinh_tu_kiem_ke_tru_hao_hut_da_ghi() -> None:
    """Phần đã ghi hao hụt không tính là tiêu thụ — nếu không là đếm hai lần."""
    khong_tru = [{"mat_hang": "sua_tuoi", "dau_ca": 25, "nhap_trong_ca": 8, "cuoi_ca": 26, "hao_hut_ghi": 0}]
    co_tru = [{"mat_hang": "sua_tuoi", "dau_ca": 25, "nhap_trong_ca": 8, "cuoi_ca": 26, "hao_hut_ghi": 3}]
    assert tinh_tu_kiem_ke(khong_tru)["sua_tuoi"] == 7.0
    assert tinh_tu_kiem_ke(co_tru)["sua_tuoi"] == 4.0


def test_tinh_tu_kiem_ke_gop_nhieu_ca() -> None:
    """Nhiều ca trong kỳ thì cộng lại."""
    muc = [
        {"mat_hang": "da", "dau_ca": 10, "nhap_trong_ca": 0, "cuoi_ca": 7, "hao_hut_ghi": 0},
        {"mat_hang": "da", "dau_ca": 7, "nhap_trong_ca": 5, "cuoi_ca": 8, "hao_hut_ghi": 0},
    ]
    assert tinh_tu_kiem_ke(muc)["da"] == 7.0


def test_tinh_tu_kiem_ke_khong_am_khi_so_lieu_nhap_sai() -> None:
    """Cuối ca lớn hơn đầu ca + nhập: kẹp về 0, không để số âm lan vào tổng."""
    muc = [{"mat_hang": "da", "dau_ca": 5, "nhap_trong_ca": 0, "cuoi_ca": 99, "hao_hut_ghi": 0}]
    assert tinh_tu_kiem_ke(muc) == {"da": 0.0}


# ── Hai vế đủ ─────────────────────────────────────────────────────────────────


def test_du_hai_ve_trong_nguong_thi_dat() -> None:
    """Hao 1.8% < 5% ⇒ đạt (cùng ca kiểm với barista-waste-audit)."""
    ra = so_hao_hut({"ca_phe_hat": 540.0}, {"ca_phe_hat": 550.0})
    dong = ra[0]
    assert dong.muc_do is LossLevel.DAT
    assert dong.lech == 10.0
    assert dong.thieu_ve == []


def test_vuot_nguong_thi_canh_bao() -> None:
    """Hao 13.3% > 5% nhưng < 15% ⇒ cảnh báo."""
    ra = so_hao_hut({"sua_tuoi": 1500.0}, {"sua_tuoi": 1700.0})
    assert ra[0].muc_do is LossLevel.CANH_BAO
    assert ra[0].ty_le_phan_tram == 13.33


def test_vuot_nguong_nghiem_trong() -> None:
    """Hao 22.2% > 15% ⇒ nghiêm trọng (cùng ca kiểm với barista-waste-audit)."""
    ra = so_hao_hut({"ca_phe_hat": 180.0}, {"ca_phe_hat": 220.0})
    assert ra[0].muc_do is LossLevel.NGHIEM_TRONG


def test_lech_am_khong_bao_dong() -> None:
    """Dùng ít hơn lý thuyết là đếm dư / công thức chưa khớp, không phải mất mát."""
    ra = so_hao_hut({"tra": 100.0}, {"tra": 80.0})
    dong = ra[0]
    assert dong.lech == -20.0
    assert dong.ty_le_phan_tram == -20.0
    assert dong.muc_do is LossLevel.DAT


def test_ly_thuyet_bang_khong_ma_co_dung_la_nghiem_trong() -> None:
    """Dùng thật mà công thức nói 0 ⇒ không có cơ sở nào cho lượng đã dùng."""
    ra = so_hao_hut({"matcha": 0.0}, {"matcha": 50.0})
    dong = ra[0]
    assert dong.muc_do is LossLevel.NGHIEM_TRONG
    assert dong.ty_le_phan_tram is None  # không chia cho 0


def test_hai_ve_bang_khong_thi_dat() -> None:
    """Có đo và bằng không, khác hẳn chưa đo."""
    ra = so_hao_hut({"banh": 0.0}, {"banh": 0.0})
    assert ra[0].muc_do is LossLevel.DAT
    assert ra[0].ly_thuyet == 0.0
    assert ra[0].thuc_te == 0.0


# ── Thiếu vế (fail-closed) ────────────────────────────────────────────────────


def test_thieu_ve_thuc_te_ra_thieu_du_lieu() -> None:
    """Có bán mà chưa kiểm kê ⇒ chưa kết luận được, không được nói 'đạt'."""
    ra = so_hao_hut({"sua_tuoi": 1500.0}, {})
    dong = ra[0]
    assert dong.muc_do is LossLevel.THIEU_DU_LIEU
    assert dong.thuc_te is None
    assert dong.ly_thuyet == 1500.0
    assert dong.lech is None
    assert dong.thieu_ve == ["thuc_te"]


def test_thieu_ve_ly_thuyet_ra_thieu_du_lieu() -> None:
    """Có kiểm kê mà chưa có đơn ⇒ chưa kết luận được."""
    ra = so_hao_hut({}, {"banh": 3.0})
    dong = ra[0]
    assert dong.muc_do is LossLevel.THIEU_DU_LIEU
    assert dong.ly_thuyet is None
    assert dong.thuc_te == 3.0
    assert dong.thieu_ve == ["ly_thuyet"]


def test_hai_ve_rong_tra_rong() -> None:
    """Không có gì thì trả rỗng, không raise, không bịa dòng."""
    assert so_hao_hut({}, {}) == []
    assert so_hao_hut(None, None) == []


def test_thieu_ve_giu_so_that_cua_ve_co() -> None:
    """Vế có số phải giữ nguyên số thật, không bị None hoá theo vế kia."""
    ra = so_hao_hut({"da": 100.0}, {})
    assert ra[0].ly_thuyet == 100.0
    assert ra[0].thuc_te is None


# ── Cơ sở tính ────────────────────────────────────────────────────────────────


def test_co_so_la_hon_hop_khi_du_hai_ve() -> None:
    ra = so_hao_hut({"da": 10.0}, {"da": 11.0})
    assert ra[0].co_so is LossBasis.HON_HOP


def test_co_so_la_kiem_ke_khi_thieu_ve() -> None:
    """Chưa đủ hai vế thì cơ sở vẫn là phiếu kiểm kê (dữ liệu đang có)."""
    ra = so_hao_hut({"da": 10.0}, {})
    assert ra[0].co_so is LossBasis.KE_HOACH_KIEM_KE


# ── Ngưỡng ────────────────────────────────────────────────────────────────────


def test_nguong_rieng_theo_mat_hang_thang_nguong_mac_dinh() -> None:
    """Sữa tươi siết 3%: mức 4% đã là cảnh báo dù mặc định 5% vẫn cho qua."""
    nguong = LossThreshold(mac_dinh_phan_tram=5.0, theo_mat_hang={"sua_tuoi": 3.0})
    ra = so_hao_hut({"sua_tuoi": 100.0}, {"sua_tuoi": 104.0}, nguong=nguong)
    assert ra[0].muc_do is LossLevel.CANH_BAO
    assert ra[0].nguong_phan_tram == 3.0


def test_nguong_rieng_khong_ap_cho_mat_hang_khac() -> None:
    nguong = LossThreshold(mac_dinh_phan_tram=5.0, theo_mat_hang={"sua_tuoi": 3.0})
    ra = so_hao_hut({"tra": 100.0}, {"tra": 104.0}, nguong=nguong)
    assert ra[0].muc_do is LossLevel.DAT
    assert ra[0].nguong_phan_tram == 5.0


# ── Sắp xếp ───────────────────────────────────────────────────────────────────


def test_sap_xep_nghiem_trong_len_truoc() -> None:
    """Dòng đáng chú ý nhất nằm trên cùng."""
    ra = so_hao_hut(
        {"a_dat": 100.0, "b_thieu": 100.0, "c_nghiem": 100.0, "d_canh": 100.0},
        {"a_dat": 100.0, "c_nghiem": 300.0, "d_canh": 110.0},
    )
    assert [d.muc_do for d in ra] == [
        LossLevel.NGHIEM_TRONG,
        LossLevel.CANH_BAO,
        LossLevel.THIEU_DU_LIEU,
        LossLevel.DAT,
    ]


# ── Làm tròn ──────────────────────────────────────────────────────────────────


def test_mat_hang_dem_bang_cai_lam_tron_nguyen() -> None:
    """Ly/bánh là số nguyên, không hiện 7.9999 cái."""
    ra = so_hao_hut({"ly": 10.0}, {"ly": 12.4})
    assert ra[0].thuc_te == 12.0
    assert ra[0].lech == 2.0


def test_mat_hang_do_luong_giu_hai_chu_so() -> None:
    ra = so_hao_hut({"sua_tuoi": 1000.0}, {"sua_tuoi": 1234.567})
    assert ra[0].thuc_te == 1234.57


# ── Nguyên nhân ───────────────────────────────────────────────────────────────


def test_xep_hang_nguyen_nhan_dem_va_sap() -> None:
    notes = [
        {"nguyen_nhan": "het_han", "mat_hang": "sua_tuoi"},
        {"nguyen_nhan": "het_han", "mat_hang": "sua_tuoi"},
        {"nguyen_nhan": "roi_do", "mat_hang": "da"},
    ]
    ra = xep_hang_nguyen_nhan(notes)
    assert [r.nguyen_nhan for r in ra] == ["het_han", "roi_do"]
    assert ra[0].so_lan == 2
    assert ra[0].ty_le_tong == 66.67
    assert ra[0].mat_hang_lien_quan == ["sua_tuoi"]


def test_xep_hang_nguyen_nhan_doc_ca_truong_ly_do() -> None:
    """Đường ghi cũ dùng `ly_do`; vẫn phải đếm được, không bỏ sót."""
    notes = [{"ly_do": "pha_sai"}, {"ly_do": "pha_sai"}]
    ra = xep_hang_nguyen_nhan(notes)
    assert ra[0].nguyen_nhan == "pha_sai"
    assert ra[0].so_lan == 2


def test_xep_hang_khong_ro_van_duoc_dem() -> None:
    """Không nêu nguyên nhân vẫn tính vào tổng — bỏ đi sẽ thổi tỷ lệ lên sai."""
    notes = [{"ghi_chu": "khong ro"}, {"nguyen_nhan": "het_han"}]
    ra = xep_hang_nguyen_nhan(notes)
    ma = {r.nguyen_nhan: r for r in ra}
    assert ma["khong_ro"].so_lan == 1
    assert ma["khong_ro"].ty_le_tong == 50.0
    assert ma["khong_ro"].nguon is LossCauseSource.HON_HOP


def test_xep_hang_rong() -> None:
    assert xep_hang_nguyen_nhan([]) == []
    assert xep_hang_nguyen_nhan([{"ghi_chu": "khong co ma nao"}]) != []


# ── Tổng hợp ──────────────────────────────────────────────────────────────────


def test_tong_hop_dem_dung_theo_muc_do() -> None:
    dong = [
        LossLine(mat_hang="a", muc_do=LossLevel.NGHIEM_TRONG, ly_thuyet=10.0, thuc_te=20.0, ty_le_phan_tram=100.0),
        LossLine(mat_hang="b", muc_do=LossLevel.CANH_BAO, ly_thuyet=10.0, thuc_te=11.0, ty_le_phan_tram=10.0),
        LossLine(mat_hang="c", muc_do=LossLevel.THIEU_DU_LIEU, ly_thuyet=10.0),
    ]
    s = tong_hop(dong)
    assert s.tong_dong == 3
    assert s.so_nghiem_trong == 1
    assert s.so_canh_bao == 1
    assert s.so_thieu_du_lieu == 1


def test_tong_hop_trung_binh_chi_tren_dong_du_hai_ve() -> None:
    """Dòng thiếu dữ liệu không được kéo trung bình — đó là bịa số."""
    dong = [
        LossLine(mat_hang="a", ly_thuyet=100.0, thuc_te=110.0, ty_le_phan_tram=10.0, muc_do=LossLevel.CANH_BAO),
        LossLine(mat_hang="b", ly_thuyet=100.0, thuc_te=120.0, ty_le_phan_tram=20.0, muc_do=LossLevel.CANH_BAO),
        LossLine(mat_hang="c", ly_thuyet=100.0, muc_do=LossLevel.THIEU_DU_LIEU),
    ]
    s = tong_hop(dong)
    assert s.ty_le_trung_binh == 15.0  # (10+20)/2, không phải (10+20+0)/3


def test_tong_hop_rong_giu_none_khong_phai_khong() -> None:
    s = tong_hop([])
    assert s.tong_dong == 0
    assert s.ty_le_trung_binh is None


def test_tong_hop_giu_co_du_lieu_mau() -> None:
    assert tong_hop([], co_du_lieu_mau=True).co_du_lieu_mau is True


# ── Đọc đơn quầy ──────────────────────────────────────────────────────────────


def test_doc_ban_theo_mon_chi_tinh_don_da_xong() -> None:
    """Đơn đang pha hoặc đã hủy thì nguyên liệu chưa ra khỏi kho."""
    don: list[dict[str, Any]] = [
        {"trang_thai": "xong", "dong": [{"mon_id": "latte", "so_luong": 2}]},
        {"trang_thai": "dang_pha", "dong": [{"mon_id": "latte", "so_luong": 5}]},
        {"trang_thai": "huy", "dong": [{"mon_id": "latte", "so_luong": 9}]},
        {"trang_thai": "cho_pha", "dong": [{"mon_id": "latte", "so_luong": 4}]},
    ]
    assert doc_ban_theo_mon(don) == {"latte": 2.0}


def test_doc_ban_theo_mon_gop_nhieu_don() -> None:
    don = [
        {"trang_thai": "xong", "dong": [{"mon_id": "latte", "so_luong": 2}]},
        {"trang_thai": "xong", "dong": [{"mon_id": "latte", "so_luong": 3}, {"mon_id": "tra_dao", "so_luong": 1}]},
    ]
    assert doc_ban_theo_mon(don) == {"latte": 5.0, "tra_dao": 1.0}


def test_doc_ban_theo_mon_bo_dong_hong() -> None:
    don = [
        {"trang_thai": "xong", "dong": [None, {"mon_id": "", "so_luong": 1}, {"mon_id": "latte", "so_luong": "x"}]},
    ]
    assert doc_ban_theo_mon(don) == {}


def test_doc_bom_theo_mon_giu_nguyen_dinh_muc() -> None:
    menu: list[dict[str, Any]] = [{"id": "latte", "bom": {"cafe_g": 18}}, {"id": "hong"}]
    assert doc_bom_theo_mon(menu) == {"latte": {"cafe_g": 18}}


# ── Tính thuần (không I/O) ────────────────────────────────────────────────────


def test_khong_import_io_trong_module_loss() -> None:
    """Cổng kiến trúc: module toán không được kéo theo tầng I/O."""
    import inspect

    from ca_agents.ag_waste import loss as mod

    src = inspect.getsource(mod)
    for cam in ("sqlite3", "httpx", "requests", "urllib", "subprocess", "socket"):
        assert f"import {cam}" not in src, f"loss.py không được import {cam}"


def test_so_hao_hut_chay_khong_can_fixture_db() -> None:
    """Hàm thuần: gọi thẳng với dict, không cần DB, không cần cấu hình gì."""
    ra = so_hao_hut({"da": 100.0}, {"da": 110.0})
    assert len(ra) == 1
    assert isinstance(ra[0], LossLine)


# ── Ghép bốn nguồn (điểm vào dùng chung cho API và agent mẹ) ────────────────────


def _phieu_kiem_ke(ngay: str, muc: list[dict[str, Any]]) -> dict[str, Any]:
    return {"ngay": ngay, "muc": muc}


def test_tinh_tu_nguon_ghep_du_bon_nguon() -> None:
    """Đường vào duy nhất: menu + đơn + kiểm kê + ghi chú ⇒ một LossSummary."""
    hom_nay = ngay_hom_nay()
    s = tinh_tu_nguon(
        menu=[{"id": "latte", "bom": {"cafe_g": 18}}],
        don_quay=[{"trang_thai": "xong", "luc": f"{hom_nay}T08:00:00", "dong": [{"mon_id": "latte", "so_luong": 10}]}],
        kiem_ke=[_phieu_kiem_ke(hom_nay, [{"mat_hang": "ca_phe_hat", "dau_ca": 500, "nhap_trong_ca": 0, "cuoi_ca": 300, "hao_hut_ghi": 0}])],
        waste_notes=[{"nguyen_nhan": "roi_do", "mat_hang": "ca_phe_hat", "luc": f"{hom_nay}T09:00:00"}],
        ky="hom_nay",
    )
    assert s.tong_dong == 1
    dong = s.dong[0]
    assert dong.mat_hang == "ca_phe_hat"
    assert dong.ten == "Cà phê hạt"
    assert dong.ly_thuyet == 180.0
    assert dong.thuc_te == 200.0
    assert dong.ty_le_phan_tram == 11.11  # 20/180 — trên 5%, dưới 15% ⇒ cảnh báo
    assert dong.muc_do is LossLevel.CANH_BAO
    assert s.nguyen_nhan_hang_dau[0].nguyen_nhan == "roi_do"
    assert s.nguyen_nhan_hang_dau[0].ten == "Rơi đổ khi làm"


def test_tinh_tu_nguon_dung_chung_mot_diem_vao() -> None:
    """API và agent mẹ gọi cùng hàm này ⇒ trang web và câu trả lời không thể lệch số.

    Khẳng định hai lần gọi với cùng dữ liệu ra cùng kết quả (tất định), để hai bề
    mặt không có cơ hội tính khác nhau.
    """
    hom_nay = ngay_hom_nay()
    kwargs = {
        "menu": [{"id": "latte", "bom": {"cafe_g": 18}}],
        "don_quay": [{"trang_thai": "xong", "luc": f"{hom_nay}T08:00:00", "dong": [{"mon_id": "latte", "so_luong": 10}]}],
        "kiem_ke": [_phieu_kiem_ke(hom_nay, [{"mat_hang": "ca_phe_hat", "dau_ca": 500, "nhap_trong_ca": 0, "cuoi_ca": 300, "hao_hut_ghi": 0}])],
        "ky": "hom_nay",
    }
    a = tinh_tu_nguon(**kwargs)  # type: ignore[arg-type]
    b = tinh_tu_nguon(**kwargs)  # type: ignore[arg-type]
    assert a.model_dump_json() == b.model_dump_json()


def test_tinh_tu_nguon_rong_khong_bia() -> None:
    """Không nguồn nào ⇒ summary rỗng, không raise, không bịa dòng."""
    s = tinh_tu_nguon(ky="hom_nay")
    assert s.tong_dong == 0
    assert s.ty_le_trung_binh is None
    assert s.co_du_lieu_mau is False


def test_tinh_tu_nguon_chi_kiem_ke_ra_thieu_ly_thuyet() -> None:
    """Chỉ có phiếu kiểm kê, chưa có đơn ⇒ chưa kết luận được, không nói 'đạt'."""
    hom_nay = ngay_hom_nay()
    s = tinh_tu_nguon(
        kiem_ke=[_phieu_kiem_ke(hom_nay, [{"mat_hang": "sua_tuoi", "dau_ca": 25, "nhap_trong_ca": 8, "cuoi_ca": 26, "hao_hut_ghi": 0}])],
        ky="hom_nay",
    )
    assert s.dong[0].muc_do is LossLevel.THIEU_DU_LIEU
    assert s.dong[0].thieu_ve == ["ly_thuyet"]
    assert s.so_thieu_du_lieu == 1


def test_tinh_tu_nguon_loc_theo_ky() -> None:
    """Kỳ hôm nay không được tính phiếu của ngày khác."""
    hom_nay = ngay_hom_nay()
    s = tinh_tu_nguon(
        kiem_ke=[
            _phieu_kiem_ke(hom_nay, [{"mat_hang": "da", "dau_ca": 10, "nhap_trong_ca": 0, "cuoi_ca": 5, "hao_hut_ghi": 0}]),
            _phieu_kiem_ke("2020-01-01", [{"mat_hang": "da", "dau_ca": 999, "nhap_trong_ca": 0, "cuoi_ca": 0, "hao_hut_ghi": 0}]),
        ],
        ky="hom_nay",
    )
    assert s.dong[0].thuc_te == 5.0


def test_tinh_tu_nguon_ky_all_nhan_moi_ngay() -> None:
    """`ky="all"` gộp mọi ngày — dùng khi xem toàn bộ lịch sử."""
    s = tinh_tu_nguon(
        kiem_ke=[
            _phieu_kiem_ke("2020-01-01", [{"mat_hang": "da", "dau_ca": 10, "nhap_trong_ca": 0, "cuoi_ca": 5, "hao_hut_ghi": 0}]),
            _phieu_kiem_ke("2021-06-06", [{"mat_hang": "da", "dau_ca": 10, "nhap_trong_ca": 0, "cuoi_ca": 3, "hao_hut_ghi": 0}]),
        ],
        ky="all",
    )
    assert s.dong[0].thuc_te == 12.0


def test_tinh_tu_nguon_giu_ban_ghi_khong_co_ngay() -> None:
    """Bản ghi thiếu mốc ngày vẫn được đếm — thà dư một dòng còn hơn bỏ sót."""
    s = tinh_tu_nguon(
        kiem_ke=[_phieu_kiem_ke("", [{"mat_hang": "da", "dau_ca": 10, "nhap_trong_ca": 0, "cuoi_ca": 4, "hao_hut_ghi": 0}])],
        ky="hom_nay",
    )
    assert s.dong[0].thuc_te == 6.0


def test_tinh_tu_nguon_danh_dau_du_lieu_mau() -> None:
    """Nhãn dữ liệu mẫu phải theo lên summary để người đọc không nhầm số mẫu."""
    hom_nay = ngay_hom_nay()
    s = tinh_tu_nguon(
        kiem_ke=[_phieu_kiem_ke(hom_nay, [{
            "id": "fx_kk_01", "nguon": "mo_phong_fixture",
            "mat_hang": "da", "dau_ca": 10, "nhap_trong_ca": 0, "cuoi_ca": 4, "hao_hut_ghi": 0,
        }])],
        ky="hom_nay",
    )
    assert s.co_du_lieu_mau is True


def test_tinh_tu_nguon_khong_danh_dau_du_lieu_that() -> None:
    hom_nay = ngay_hom_nay()
    s = tinh_tu_nguon(
        kiem_ke=[_phieu_kiem_ke(hom_nay, [{"id": "kk_01", "mat_hang": "da", "dau_ca": 10, "nhap_trong_ca": 0, "cuoi_ca": 4, "hao_hut_ghi": 0}])],
        ky="hom_nay",
    )
    assert s.co_du_lieu_mau is False


def test_tinh_tu_nguon_doc_ngay_tu_nhieu_truong() -> None:
    """Bản ghi thật ghi `luc`; cả fixture/MinIO ghi `created_at`.

    Đọc sai trường là bỏ sót nguyên một nguồn. Bản tổng kết ngày của worker từng
    luôn ra 0 vì lý do này.
    """
    hom_nay = ngay_hom_nay()
    s = tinh_tu_nguon(
        waste_notes=[
            {"nguyen_nhan": "het_han", "luc": f"{hom_nay}T10:00:00"},
            {"nguyen_nhan": "roi_do", "created_at": f"{hom_nay}T11:00:00"},
        ],
        ky="hom_nay",
    )
    ma = {r.nguyen_nhan: r.so_lan for r in s.nguyen_nhan_hang_dau}
    assert ma == {"het_han": 1, "roi_do": 1}


def test_tinh_tu_nguon_nguon_la_khong_raise() -> None:
    """Nguồn rác không làm sập trang hao hụt."""
    s = tinh_tu_nguon(kiem_ke=[None, "chuoi", 42], don_quay=[None], menu=[None], ky="hom_nay")  # type: ignore[list-item]
    assert s.tong_dong == 0
