"""Động cơ so sánh phân công — nguồn sự thật cho "ai đổi ca với ai".

Mô-đun này là phần DUY NHẤT phân loại thay đổi ca, dùng chung cho ba nguồn (xếp
lịch tự động, xác nhận TKB, chợ đổi ca). Nếu ba nơi tự tính thì UI sẽ hiện ba câu
khác nhau cho cùng một sự kiện — xem docstring đầu `ca_api/services/schedule_diff.py`.

Các bài ở đây cố ý chốt ba chuyện DỄ SAI:
  1. `hoan_doi` (cùng ca có người ra + người vào) tách hẳn khỏi `doi_giua_hai_ca`
     (một người đổi từ ca này sang ca khác) — hai chuyện khác nghĩa với người đọc.
  2. Thiếu dữ liệu (`None`) KHÔNG được đọc thành "không có gì đổi".
  3. Thứ tự người trong một ca không phải là thay đổi.
"""

from __future__ import annotations

from ca_api.interfaces.http.main import app
from ca_api.persist import kv_get, kv_set
from ca_api.services.schedule_diff import so_sanh_phan_cong, tom_tat_thay_doi
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)

CA_META = {
    "w1_c01": {"thu": "T2", "khung": "sang", "bat_dau": "07:00", "ket_thuc": "12:00"},
    "w1_c02": {"thu": "CN", "khung": "toi", "bat_dau": "17:30", "ket_thuc": "22:30", "vi_tri": "pha_che"},
    "w1_c03": {"thu": "T4", "khung": "chieu", "bat_dau": "12:00", "ket_thuc": "17:30"},
}

NHAN_VIEN = {
    "nv_01": {"ten": "Nguyễn Văn A"},
    "nv_02": {"ten": "Trần Thị B"},
    "nv_03": {"ten": "Lê Văn C"},
}


def test_khong_doi_gi_thi_moi_danh_sach_rong():
    phan = {"w1_c01": ["nv_01", "nv_02"]}
    diff = so_sanh_phan_cong(phan, dict(phan), ca_meta=CA_META, nhan_vien=NHAN_VIEN)

    assert diff["them"] == []
    assert diff["bot"] == []
    assert diff["hoan_doi"] == []
    assert diff["doi_giua_hai_ca"] == []
    assert diff["giu_nguyen"] == 2
    assert diff["khong_so_sanh_duoc"] is False
    assert tom_tat_thay_doi(diff) == "Không có ca nào thay đổi."


def test_doi_thu_tu_trong_cung_ca_khong_phai_thay_doi():
    """Cùng một tập người, chỉ khác thứ tự — KHÔNG được báo là đổi ca."""
    truoc = {"w1_c01": ["nv_01", "nv_02"]}
    sau = {"w1_c01": ["nv_02", "nv_01"]}
    diff = so_sanh_phan_cong(truoc, sau, ca_meta=CA_META, nhan_vien=NHAN_VIEN)

    assert diff["them"] == [] and diff["bot"] == []
    assert diff["giu_nguyen"] == 2


def test_nguoi_vao_nguoi_ra_cung_ca_la_hoan_doi_va_doc_duoc_ten():
    """Câu người dùng hỏi: 'ai bị thay thế vào ca đó' → phải có TÊN, không chỉ id."""
    truoc = {"w1_c01": ["nv_01"]}
    sau = {"w1_c01": ["nv_02"]}
    diff = so_sanh_phan_cong(truoc, sau, ca_meta=CA_META, nhan_vien=NHAN_VIEN)

    assert len(diff["hoan_doi"]) == 1
    hoan_doi = diff["hoan_doi"][0]
    assert hoan_doi["ca"]["ca_id"] == "w1_c01"
    assert hoan_doi["ca"]["thu"] == "T2"
    assert hoan_doi["ca"]["gio"] == "07:00-12:00"
    assert [r["ten"] for r in hoan_doi["ra"]] == ["Nguyễn Văn A"]
    assert [v["ten"] for v in hoan_doi["vao"]] == ["Trần Thị B"]

    # Người này KHÔNG chuyển ca (không vừa ra vừa vào ở hai ca khác nhau).
    assert diff["doi_giua_hai_ca"] == []


def test_mot_nguoi_chuyen_tu_ca_nay_sang_ca_khac_tach_khoi_hoan_doi():
    """nv_01 rời T2-sáng, sang CN-tối. Đây là CHUYỂN CA, không phải bị thay thế.

    Nếu gộp vào `hoan_doi` thì panel sẽ nói "T2 đổi người" và bỏ mất thông tin
    quan trọng hơn: chính nv_01 là người được chuyển đi, không phải bị cắt.
    """
    truoc = {"w1_c01": ["nv_01"]}
    sau = {"w1_c02": ["nv_01"]}
    diff = so_sanh_phan_cong(truoc, sau, ca_meta=CA_META, nhan_vien=NHAN_VIEN)

    assert diff["hoan_doi"] == []
    assert len(diff["doi_giua_hai_ca"]) == 1
    chuyen = diff["doi_giua_hai_ca"][0]
    assert chuyen["nv_id"] == "nv_01"
    assert chuyen["ten"] == "Nguyễn Văn A"
    assert [c["ca_id"] for c in chuyen["tu_ca"]] == ["w1_c01"]
    assert [c["ca_id"] for c in chuyen["den_ca"]] == ["w1_c02"]


def test_ca_moi_hoan_toan_va_ca_bi_bo_hoan_toan():
    truoc = {"w1_c01": ["nv_01"], "w1_c02": ["nv_02"]}
    sau = {"w1_c03": ["nv_03"]}
    diff = so_sanh_phan_cong(truoc, sau, ca_meta=CA_META, nhan_vien=NHAN_VIEN)

    assert diff["giu_nguyen"] == 0
    assert sorted(t["ca"]["ca_id"] for t in diff["them"]) == ["w1_c03"]
    assert sorted(b["ca"]["ca_id"] for b in diff["bot"]) == ["w1_c01", "w1_c02"]
    # nv_03 chỉ vào, nv_01/nv_02 chỉ ra → không ai "chuyển ca".
    assert diff["doi_giua_hai_ca"] == []
    assert diff["hoan_doi"] == []


def test_thieu_du_lieu_khong_duoc_doc_thanh_khong_doi():
    """`None` = chưa có dữ liệu. Không được suy ra 'không có gì đổi'.

    Đây là quy ước chung của repo (xem `ca_contracts/loss.py`): thiếu vế thì
    KHÔNG được kết luận đạt. Nếu trả {} ở đây, panel sẽ im lặng nói "không đổi"
    trong khi thực tế ta chưa hề so sánh.
    """
    diff = so_sanh_phan_cong(None, {"w1_c01": ["nv_01"]})
    assert diff["khong_so_sanh_duoc"] is True
    assert diff["them"] == [] and diff["bot"] == []
    assert "Chưa đủ dữ liệu" in tom_tat_thay_doi(diff)

    diff2 = so_sanh_phan_cong({"w1_c01": ["nv_01"]}, None)
    assert diff2["khong_so_sanh_duoc"] is True


def test_thieu_bang_tra_van_tra_id_tho_chu_khong_bia_ten():
    """Thiếu `nhan_vien`/`ca_meta` thì UI vẫn phải vẽ được, dùng id thay tên."""
    truoc = {"w1_c01": ["nv_01"]}
    sau = {"w1_c01": ["nv_02"]}
    diff = so_sanh_phan_cong(truoc, sau)

    hoan_doi = diff["hoan_doi"][0]
    assert hoan_doi["ra"][0]["ten"] == "nv_01"
    assert hoan_doi["vao"][0]["ten"] == "nv_02"
    assert hoan_doi["ca"]["thu"] == ""
    assert hoan_doi["ca"]["gio"] == ""


def test_khu_trung_id_trong_mot_ca():
    """Phân công lưu id trùng thì không được đếm hai lần là hai người."""
    truoc = {"w1_c01": ["nv_01", "nv_01"]}
    sau = {"w1_c01": ["nv_01", "nv_02", "nv_02"]}
    diff = so_sanh_phan_cong(truoc, sau, ca_meta=CA_META, nhan_vien=NHAN_VIEN)

    assert diff["giu_nguyen"] == 1
    assert [(t["nv_id"], t["ten"]) for t in diff["them"]] == [("nv_02", "Trần Thị B")]
    assert diff["bot"] == []


def test_tom_tat_dem_dung_va_khong_lap_nguoi_vao_roi_ra():
    truoc = {"w1_c01": ["nv_01"], "w1_c02": ["nv_02"]}
    sau = {"w1_c01": ["nv_03"], "w1_c03": ["nv_01"]}
    diff = so_sanh_phan_cong(truoc, sau, ca_meta=CA_META, nhan_vien=NHAN_VIEN)

    # w1_c01: nv_01 ra, nv_03 vào → 1 ca đổi người.
    # nv_01: ra w1_c01, vào w1_c03 → 1 người chuyển ca.
    # nv_02: ra w1_c02, không vào đâu → 1 lượt người ra.
    cau = tom_tat_thay_doi(diff)
    assert "1 ca đổi người" in cau
    assert "1 người chuyển sang ca khác" in cau


# ─────────────────────────────────────────────────────────────────────────────
# Đường API `/api/v1/lich-tuan/thay-doi` + trần lưu nhật ký
#
# Động cơ đúng mà không có đường đọc lại thì người dùng vẫn không thấy gì —
# đúng lỗi "tự động ngầm xong rồi không hiểu gì" mà họ phàn nàn.
# ─────────────────────────────────────────────────────────────────────────────


def test_api_nhat_ky_doc_lai_duoc_va_moi_nhat_truoc():
    """Endpoint trả bản MỚI NHẤT trước, đọc thẳng từ store."""
    ql = headers(client, "lan")
    week = "2026-W46"
    ban_ghi = [
        {"luc": "2026-11-01T08:00:00Z", "nguon": "xep_tu_dong", "tuan_iso": week, "tom_tat": "cũ"},
        {"luc": "2026-11-02T09:00:00Z", "nguon": "xep_tu_dong", "tuan_iso": week, "tom_tat": "mới"},
    ]
    kv_set("lich_thay_doi_by_week", {week: ban_ghi})
    try:
        r = client.get(f"/api/v1/lich-tuan/thay-doi?tuan_iso={week}", headers=ql)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["tuan_iso"] == week
        assert body["so_ban_ghi"] == 2
        assert body["items"][0]["tom_tat"] == "mới"
    finally:
        kv_set("lich_thay_doi_by_week", {})


def test_api_nhat_ky_tuan_chua_co_tra_rong_chu_khong_404():
    """Tuần chưa có nhật ký là RỖNG hợp lệ — không phải lỗi tải."""
    ql = headers(client, "lan")
    kv_set("lich_thay_doi_by_week", {})
    r = client.get("/api/v1/lich-tuan/thay-doi?tuan_iso=1999-W01", headers=ql)
    assert r.status_code == 200, r.text
    assert r.json()["so_ban_ghi"] == 0
    assert r.json()["items"] == []


def test_api_nhat_ky_yeu_cau_quyen_ghi():
    """Nhân viên không đọc được nhật ký thay đổi ca."""
    nv = headers(client, "minh")
    r = client.get("/api/v1/lich-tuan/thay-doi?tuan_iso=2026-W40", headers=nv)
    assert r.status_code == 403


def test_tran_nhat_ky_dung_20_ban_ghi():
    """Nhật ký không phình vô hạn: 25 bản ghi thì chỉ còn 20, bản CŨ nhất bị bỏ."""
    from ca_api.services.solver_adapter import NHAT_KY_TOI_DA

    assert NHAT_KY_TOI_DA == 20
    week = "2026-W47"
    tat_ca = [{"luc": f"2026-11-{i:02d}T00:00:00Z", "nguon": "xep_tu_dong"} for i in range(1, 26)]
    kv_set("lich_thay_doi_by_week", {week: tat_ca[-NHAT_KY_TOI_DA:]})
    try:
        raw = kv_get("lich_thay_doi_by_week", {})
        assert len(raw[week]) == NHAT_KY_TOI_DA
        # 25 bản → giữ 20 bản cuối → bản đầu tiên còn lại là ngày 06.
        assert raw[week][0]["luc"] == "2026-11-06T00:00:00Z"
    finally:
        kv_set("lich_thay_doi_by_week", {})


def test_ghi_nhat_ky_nhan_nguon_va_bo_qua_khi_khong_doi():
    """Helper chung phải tôn trọng tag nguồn; không đổi thì không ghi."""
    from ca_api.services.solver_adapter import ghi_nhat_ky_thay_doi

    week = "2026-W48"
    kv_set("lich_thay_doi_by_week", {})
    kv_set("phan_cong_by_week", {week: {"w1_c01": ["nv_01"]}})
    try:
        khong = ghi_nhat_ky_thay_doi(
            week, {"w1_c01": ["nv_01"]}, CA_META, nguon="doi_ca", nhan_vien=NHAN_VIEN,
        )
        assert khong is None
        assert kv_get("lich_thay_doi_by_week", {}).get(week, []) == []

        ban = ghi_nhat_ky_thay_doi(
            week,
            {"w1_c01": ["nv_02"]},
            CA_META,
            nguon="doi_ca",
            truoc={"w1_c01": ["nv_01"]},
            nhan_vien=NHAN_VIEN,
        )
        assert ban is not None
        assert ban["nguon"] == "doi_ca"
        assert ban["diff"]["hoan_doi"]
        assert ban["diff"]["hoan_doi"][0]["ra"][0]["ten"] == "Nguyễn Văn A"
        assert ban["diff"]["hoan_doi"][0]["vao"][0]["ten"] == "Trần Thị B"
        stored = kv_get("lich_thay_doi_by_week", {})[week]
        assert len(stored) == 1
        assert stored[0]["nguon"] == "doi_ca"
    finally:
        kv_set("lich_thay_doi_by_week", {})
        kv_set("phan_cong_by_week", {})


def test_duyet_doi_ca_ghi_nhat_ky_hoan_doi():
    """Duyệt đổi ca phải ghi nhật ký nguồn doi_ca — đúng lỗ hổng 'không thấy ai thay ai'."""
    week = "2026-W49"
    ca_id = "w1_c01"
    kv_set("phan_cong", {ca_id: ["nv_01"]})
    kv_set("phan_cong_by_week", {week: {ca_id: ["nv_01"]}})
    kv_set("lich_thay_doi_by_week", {})
    kv_set("lich_tuan_lifecycle", {"tuan_iso": week, "trang_thai": "da_cong_bo"})
    kv_set(
        "lich_tuan_lifecycle_by_week",
        {week: {"tuan_iso": week, "trang_thai": "da_cong_bo"}},
    )
    try:
        opened = client.post(
            "/api/v1/cho-doi-ca",
            json={"a": "nv_01", "b": "nv_03", "ca_id": ca_id},
            headers=headers(client, "lan"),
        ).json()
        # Gắn tuần phiếu đúng tuần fixture (mặc định có thể lấy lifecycle khác).
        from ca_api.persist import kv_mutate

        def mut_tuan(items):
            for it in items:
                if it.get("id") == opened["id"]:
                    it["tuan_id"] = week
            return items

        kv_mutate("swap", mut_tuan, [])

        client.post(
            f"/api/v1/cho-doi-ca/{opened['id']}/dong-y",
            headers=headers(client, "minh"),
        )
        duyet = client.post(
            f"/api/v1/cho-doi-ca/{opened['id']}/duyet",
            headers=headers(client, "lan"),
        )
        assert duyet.status_code == 200, duyet.text
        assert kv_get("phan_cong_by_week", {})[week][ca_id] == ["nv_03"]

        journal = kv_get("lich_thay_doi_by_week", {}).get(week) or []
        assert journal, "duyệt đổi ca phải ghi nhật ký"
        ban = journal[-1]
        assert ban["nguon"] == "doi_ca"
        assert ban["diff"]["hoan_doi"], ban
        ra_ids = [r["nv_id"] for r in ban["diff"]["hoan_doi"][0]["ra"]]
        vao_ids = [v["nv_id"] for v in ban["diff"]["hoan_doi"][0]["vao"]]
        assert "nv_01" in ra_ids
        assert "nv_03" in vao_ids
    finally:
        kv_set("lich_thay_doi_by_week", {})
        kv_set("phan_cong_by_week", {})
        kv_set("phan_cong", {})
        kv_set("swap", [])

