"""Danh mục sản phẩm & ảnh thẻ — plan 260923-1736 phase 6.

Khẳng định:

1. Danh mục phủ đủ nhóm sản phẩm, mã nguyên liệu khớp giữa ba nguồn.
2. Nạp danh mục là idempotent và không đụng món ngoài danh mục.
3. Ảnh sinh tại máy, tất định (cùng id ⇒ cùng byte), không cần mạng.
4. `GET /api/v1/menu/{id}/anh` trả ảnh cho **mọi** món kể cả chưa chạy script sinh.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ca_api.interfaces.http.main import app
from ca_api.persist import menu_get, menu_list, menu_upsert
from ca_api.services.menu_image import KICH_THUOC, bam_anh, bytes_anh, ve_anh
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)

ROOT = Path(__file__).resolve().parents[4]
DANH_MUC = ROOT / "data" / "seed" / "danh-muc.json"


def _doc() -> dict[str, Any]:
    return json.loads(DANH_MUC.read_text(encoding="utf-8"))


def _mon() -> list[dict[str, Any]]:
    return list(_doc()["mon"])


# ── Danh mục ──────────────────────────────────────────────────────────────────


def test_danh_muc_du_nhom_san_pham() -> None:
    """Phải có cà phê, trà, nước đóng chai, sinh tố, bánh và nguyên liệu."""
    nhom = {m["nhom"] for m in _mon()}
    for bat_buoc in ("ca_phe", "tra", "nuoc_dong_chai", "sinh_to", "banh", "nguyen_lieu"):
        assert bat_buoc in nhom, f"danh mục thiếu nhóm {bat_buoc}"


def test_danh_muc_du_lon() -> None:
    """Ít nhất 45 món — quán thật có menu dài hơn bốn món mặc định."""
    assert len(_mon()) >= 45


def test_moi_mon_co_cong_thuc() -> None:
    """Không có định mức thì không tính được vế lý thuyết của hao hụt."""
    for m in _mon():
        assert m.get("bom"), f"{m['id']} thiếu công thức"
        for nl, dm in m["bom"].items():
            assert dm > 0, f"{m['id']}/{nl} định mức phải > 0"


def test_ma_mon_khong_trung() -> None:
    ids = [m["id"] for m in _mon()]
    assert len(ids) == len(set(ids)), "có mã món trùng"


def test_ma_nguyen_lieu_khop_voi_bom_editor() -> None:
    """Mã nguyên liệu phải khớp danh sách chọn ở `bom-editor.tsx`.

    Lệch mã thì công thức lưu từ UI và công thức nạp từ danh mục là hai hệ khác
    nhau, và phép tính hao hụt sẽ không ghép được hai vế.
    """
    hop_le = {
        "ca_phe_hat", "cafe_g", "sua_tuoi", "sua_dac", "tra", "matcha", "dao",
        "da", "banh", "ly", "nuoc_dong_chai", "duong", "syrup", "kem",
        "ong_hut", "trai_cay",
    }
    for m in _mon():
        la = set(m["bom"]) - hop_le
        assert not la, f"{m['id']} dùng mã nguyên liệu lạ: {la}"


def test_co_nuoc_dong_chai_trong_danh_muc() -> None:
    """Nhóm nước đóng chai là thứ trước đây hoàn toàn thiếu."""
    nuoc = [m for m in _mon() if m["nhom"] == "nuoc_dong_chai"]
    assert len(nuoc) >= 5


def test_danh_muc_qua_kiem_tra_cua_script() -> None:
    """`kiem_tra()` của script nạp phải nói danh mục hợp lệ."""
    import importlib.util
    import sys

    path = ROOT / "scripts" / "seed_danh_muc.py"
    spec = importlib.util.spec_from_file_location("seed_danh_muc", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    assert mod.kiem_tra(_doc()) == []


# ── Nạp idempotent ────────────────────────────────────────────────────────────


def test_nap_danh_muc_idempotent() -> None:
    """Nạp hai lần không nhân bản, và món ngoài danh mục còn nguyên."""
    import importlib.util
    import sys

    path = ROOT / "scripts" / "seed_danh_muc.py"
    spec = importlib.util.spec_from_file_location("seed_danh_muc", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    menu_upsert({"id": "mon_quan_tu_them", "ten": "Món quán tự thêm", "gia": 99000, "bom": {"da": 50}})

    mod.nap(_doc())
    lan1 = {m["id"] for m in menu_list(gom_an=True)}
    mod.nap(_doc())
    lan2 = {m["id"] for m in menu_list(gom_an=True)}

    assert lan1 == lan2, "nạp lần hai làm đổi danh mục"
    assert "mon_quan_tu_them" in lan2, "món ngoài danh mục bị xoá"
    assert len([m for m in _mon() if m["id"] in lan2]) == len(_mon())


# ── Ảnh sinh tại máy ──────────────────────────────────────────────────────────


def test_anh_tat_dinh_cung_id_cung_byte() -> None:
    """Cùng món ⇒ cùng byte. Không có `random` thì ảnh mới không nhảy loạn."""
    m = {"id": "latte", "ten": "Latte", "gia": 42000, "nhom": "ca_phe"}
    assert bytes_anh(m) == bytes_anh(m)
    assert bam_anh(m) == bam_anh(m)


def test_anh_khac_mon_thi_khac_byte() -> None:
    a = bytes_anh({"id": "latte", "ten": "Latte", "gia": 42000, "nhom": "ca_phe"})
    b = bytes_anh({"id": "tra_dao", "ten": "Trà đào", "gia": 35000, "nhom": "tra"})
    assert a != b


def test_anh_dung_kich_thuoc() -> None:
    img = ve_anh({"id": "da", "ten": "Đá", "nhom": "nguyen_lieu"})
    assert img.size == (KICH_THUOC, KICH_THUOC)


def test_anh_thieu_id_thi_bao_loi() -> None:
    import pytest

    with pytest.raises(ValueError):
        ve_anh({"ten": "Không có id"})


def test_anh_la_png_hop_le() -> None:
    """Chữ ký PNG — để `<img>` render được, không trả bytes rác."""
    raw = bytes_anh({"id": "bac_xiu", "ten": "Bạc xỉu", "gia": 32000, "nhom": "ca_phe"})
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"


def test_moi_mon_trong_danh_muc_sinh_duoc_anh() -> None:
    """Không món nào được vỡ khi sinh ảnh — kể cả tên dài, giá 0, nhóm lạ."""
    for m in _mon():
        raw = bytes_anh({"id": m["id"], "ten": m["ten"], "gia": m["gia"], "nhom": m["nhom"]})
        assert raw[:8] == b"\x89PNG\r\n\x1a\n", f"{m['id']} không ra PNG"


# ── Bề mặt HTTP ảnh ───────────────────────────────────────────────────────────


def test_anh_mon_chua_tai_len_van_tra_anh() -> None:
    """Bậc 3: máy chưa chạy script sinh ảnh thì endpoint tự sinh tại chỗ.

    Đây là chỗ chốt ràng buộc demo offline (§14.9) — lưới menu không được rơi về
    chữ cái đầu chỉ vì thiếu file.
    """
    menu_upsert({"id": "mon_anh_tu_sinh", "ten": "Món ảnh tự sinh", "gia": 30000, "bom": {"ca_phe_hat": 18}})
    r = client.get("/api/v1/menu/mon_anh_tu_sinh/anh")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/png")
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_anh_mon_khong_ton_tai_tra_404() -> None:
    r = client.get("/api/v1/menu/khong_co_mon_nay/anh")
    assert r.status_code == 404


def test_anh_mon_id_khong_hop_le_tra_404() -> None:
    """Mã món sai định dạng không được đi vào đường sinh ảnh."""
    r = client.get("/api/v1/menu/AB!!/anh")
    assert r.status_code == 404


def test_anh_mon_tu_tai_len_thang_anh_tu_sinh() -> None:
    """Ảnh do quán tải lên phải thắng ảnh tự sinh — không được ghi đè ảnh thật."""
    from ca_api.interfaces.http.pos import _menu_image_dir

    menu_upsert({"id": "mon_co_anh_that", "ten": "Món có ảnh thật", "gia": 30000, "bom": {"da": 100}})
    # PNG 1×1 hợp lệ, nhỏ nhất có thể
    that = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )
    (_menu_image_dir() / "mon_co_anh_that.png").write_bytes(that)

    r = client.get("/api/v1/menu/mon_co_anh_that/anh")
    assert r.status_code == 200
    assert r.content == that, "ảnh tự sinh đã ghi đè ảnh quán tải lên"


def test_anh_tra_cho_moi_mon_da_nap() -> None:
    """Nạp danh mục rồi mọi món phải trả ảnh — không món nào 404."""
    for m in _mon()[:12]:
        menu_upsert({
            "id": m["id"],
            "ten": m["ten"],
            "gia": m["gia"],
            "bom": {str(k): float(v) for k, v in m["bom"].items()},
        })
        r = client.get(f"/api/v1/menu/{m['id']}/anh")
        assert r.status_code == 200, f"{m['id']} không trả ảnh"
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_anh_public_khong_can_token() -> None:
    """`<img>` không gửi được Bearer — endpoint ảnh phải public."""
    menu_upsert({"id": "mon_anh_public", "ten": "Món ảnh public", "gia": 30000, "bom": {"da": 100}})
    r = client.get("/api/v1/menu/mon_anh_public/anh")
    assert r.status_code == 200


def test_menu_quan_tri_thay_du_mon_sau_khi_nap() -> None:
    """Nạp danh mục rồi chủ quán phải thấy đủ món trong trang quản trị."""
    import importlib.util
    import sys

    path = ROOT / "scripts" / "seed_danh_muc.py"
    spec = importlib.util.spec_from_file_location("seed_danh_muc", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    mod.nap(_doc())

    r = client.get("/api/v1/menu/quan-tri", headers=headers(client, "hung"))
    assert r.status_code == 200, r.text
    ids = {m["id"] for m in r.json()["items"]}
    for m in _mon():
        assert m["id"] in ids, f"{m['id']} không có trong menu quản trị"


def test_nuoc_dong_chai_co_trong_menu_mac_dinh() -> None:
    """Danh mục mặc định của persist phải có nước đóng chai và bánh kèm."""
    from ca_api.persist import _MENU_MAC_DINH

    nguyen_lieu = {k for _, _, _, bom, _ in _MENU_MAC_DINH for k in bom}
    assert "nuoc_dong_chai" in nguyen_lieu, "menu mặc định thiếu nước đóng chai"
    assert "banh" in nguyen_lieu, "menu mặc định thiếu bánh kèm"


def test_menu_get_tra_dung_mon_vua_upsert() -> None:
    menu_upsert({"id": "mon_kiem_get", "ten": "Món kiểm get", "gia": 12345, "bom": {"tra": 8}})
    mon = menu_get("mon_kiem_get")
    assert mon is not None
    assert mon["gia"] == 12345
    assert mon["bom"] == {"tra": 8}


# ── Ràng buộc dữ liệu menu/đơn (chặt lỗi đợt 8) ─────────────────────────────
#
# Ba lỗi dưới đây đều từng làm màn hình quầy hỏng mà không có một dòng cảnh báo
# nào, nên phải có test giữ. Nguồn gốc chung: dữ liệu quầy được ghi từ nhiều nơi
# (API, seeder Quảnverse, script dọn) mà không có một chỗ nào kiểm tra hình dạng.


def test_menu_khong_co_mon_trung_ten() -> None:
    """Hai món cùng tên ở hai giá là lỗi dữ liệu, không phải hai món.

    Đã xảy ra thật: `mon_den` "Cà phê đen" 25.000 cạnh `fx_mon_ca_phe_den`
    "Ca phe den" 29.000, `mon_da` "Bạc xỉu" cạnh `fx_mon_bac_xiu`. Nhân viên
    không biết chọn cái nào, và báo cáo doanh thu tách đôi cho cùng một ly.
    """
    ten = [m["ten"].strip().casefold() for m in menu_list(gom_an=True)]
    trung = sorted({t for t in ten if ten.count(t) > 1})
    assert not trung, f"menu có món trùng tên: {trung}"


def test_moi_mon_trong_menu_co_nhom_hop_le() -> None:
    """`nhom` phải là mã trong danh mục, hoặc rỗng để tầng đọc tự suy.

    Mã lạ thì UI bỏ qua món đó (`quay/page.tsx` chỉ vẽ nhóm có trong
    `NHOM_MON_THU_TU`) → món biến mất khỏi quầy im lặng. Migration 0018 và
    `PUT /api/v1/menu/{id}` đã chặn, test này giữ cho dữ liệu cũ trong DB.
    """
    hop_le = {"ca_phe", "tra", "sinh_to", "banh", "nuoc_dong_chai", "nguyen_lieu", ""}
    la = {m["id"]: m.get("nhom", "") for m in menu_list(gom_an=True)}
    ngoai = {k: v for k, v in la.items() if v not in hop_le}
    assert not ngoai, f"món có nhóm ngoài danh mục: {ngoai}"


def test_ten_mon_tieng_viet_co_dau() -> None:
    """Món tiếng Việt phải viết có dấu — tên là thứ nhân viên đọc để gọi món.

    Fixture `fx_mon_*` từng ghi "Ca phe den", "Combo sang", "Matcha sua"…
    Tên không dấu thì nhân viên gọi cho khách sai tên món.
    """
    import unicodedata

    for m in menu_list(gom_an=True):
        ten = m["ten"]
        khoa = unicodedata.normalize("NFD", ten.replace("đ", "d").replace("Đ", "D"))
        khoa = "".join(c for c in khoa if not unicodedata.combining(c)).casefold().strip()
        assert ten.strip().casefold() != khoa, f"{m['id']} tên mất dấu: {ten!r}"


def test_don_luon_co_day_du_ten_va_so_luong() -> None:
    """Mọi dòng đơn phải đủ `{mon_id,ten,so_luong,gia}`.

    Seeder Quảnverse từng ghi `[{"mon": ..., "sl": ...}]` khiến UI đọc
    `line.ten` và `line.so_luong` ra `undefined`: phiếu pha chế trống chỉ còn
    dấu "×" và không hủy được. Đây là test chặt đúng lỗi đó.
    """
    from ca_api.persist import don_list
    from ca_api.services.quanverse_demo import setup

    # Gọi `setup()` để khẳng định này KHÔNG rỗng: nếu chỉ đọc `don_list()` mà DB
    # test chưa có đơn nào thì vòng lặp không chạy lần nào và test luôn xanh —
    # đúng kiểu test tự nó không bắt được gì.
    setup()

    for don in don_list():
        assert don["dong"], f"đơn {don['id']} không có dòng món nào"
        for dong in don["dong"]:
            assert dong.get("mon_id"), f"đơn {don['id']} thiếu mon_id"
            assert dong.get("ten"), f"đơn {don['id']} thiếu tên món"
            assert isinstance(dong.get("so_luong"), int), f"đơn {don['id']} thiếu so_luong"
            assert isinstance(dong.get("gia"), int), f"đơn {don['id']} thiếu gia"
            assert dong["so_luong"] >= 1, f"đơn {don['id']} có so_luong < 1"


def test_don_luon_dung_ma_thanh_toan() -> None:
    """`thanh_toan` phải là mã trong `DonQuay`, nếu không UI hiện "Chưa rõ".

    Seeder từng ghi `"chua_tt"` (mã thật là `chua_thu`) nên mọi đơn demo hiện
    "Chưa rõ thanh toán" — thông tin mất hoàn toàn trên màn hình.
    """
    from ca_api.persist import don_list

    hop_le = {"tien_mat", "da_ck", "chua_thu"}
    la = {d["id"]: d["thanh_toan"] for d in don_list() if d["thanh_toan"] not in hop_le}
    assert not la, f"đơn có mã thanh toán không hợp lệ: {la}"


def test_setup_quanverse_viet_don_dung_hinh_dang() -> None:
    """`quanverse_demo.setup()` phải ghi đơn đúng hình dạng, chạy lại cũng vậy.

    Đây là nơi sinh ra dữ liệu hỏng, nên chặn ngay tại đây thay vì đợi migration
    0018 dọn hậu quả. Idempotent: gọi hai lần phải không sinh thêm đơn.
    """
    from ca_api.persist import don_list
    from ca_api.services.quanverse_demo import setup

    truoc = {d["id"] for d in don_list() if d["id"].startswith("demo_qv_")}
    a = setup()
    b = setup()
    assert a["orders_created"] == 0 or not truoc, "chạy lại vẫn tạo đơn mới"
    assert b["orders_created"] == 0, "chạy lần hai vẫn tạo đơn mới"

    hop_le = {"tien_mat", "da_ck", "chua_thu"}
    for don in don_list():
        if not don["id"].startswith("demo_qv_"):
            continue
        assert don["thanh_toan"] in hop_le, f"{don['id']} thanh toán sai: {don['thanh_toan']}"
        assert don["dong"], f"{don['id']} không có dòng món"
        for dong in don["dong"]:
            assert set(dong) >= {"mon_id", "ten", "so_luong", "gia"}, f"{don['id']} dong thiếu khoá"
            assert dong["ten"], f"{don['id']} tên món rỗng"


def test_quanverse_demo_don_co_mon_that_khong_phai_ten_bia() -> None:
    """Đơn demo phải trỏ tới món ĐANG CÓ trong menu, không tự bịa tên.

    Bản trước ghi cứng tên "Ca phe sua" không kèm `mon_id`; món đó còn không
    tồn tại sau khi menu được dọn, nên tiêu thụ BOM không ghi được cho đơn đó.
    """
    from ca_api.persist import don_list
    from ca_api.services.quanverse_demo import setup

    setup()
    co_mon = {m["id"] for m in menu_list()}
    for don in don_list():
        if not don["id"].startswith("demo_qv_"):
            continue
        for dong in don["dong"]:
            assert dong["mon_id"] in co_mon, f"{don['id']} trỏ môn không có: {dong['mon_id']}"
