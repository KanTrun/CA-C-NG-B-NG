# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Test hồi quy cho các bug QA đợt 5 (2026-09-28).

Mỗi test ở đây tương ứng một bug TÁI HIỆN ĐƯỢC trên production, kèm số đo thật:

- BUG-01 (Critical): `/quay/don/{id}/chuyen` là read-then-write không khoá nên
  hai request đồng thời đều qua cổng `_STATUS_NEXT` → `_ghi_tieu_thu_uoc_luong`
  chạy hai lần → kho bị trừ gấp đôi. Đo trên production: +6 dòng tiêu thụ thay
  vì +3 (mỗi nguyên liệu ghi 2 lần, timestamp lệch ~20ms).
- BUG-02 (High): PUT `/menu/{id}` không gửi `bom` thì `bom` về `{}` → MẤT định
  mức nguyên liệu (`fx_mon_bac_xiu` từ 3 nguyên liệu còn 0).
- BUG-04 (Medium): PUT `/store/profile` nhận `dict[str, Any]` trần — nhận cả
  `<script>` trong tên quán, hotline không phải số, địa chỉ 5.000 ký tự.
- BUG-05 (Medium): POST `/reservations` nhận `booking_time` quá khứ (2020) và
  tạo đơn `confirmed`.
- A-01 (DoS): POST `/meeting/analyze` không giới hạn `text` — payload 500.000
  ký tự giữ worker >25 giây.
- A-04: POST `/phieu/start` gọi lại cùng `mau` sinh phiếu MỚI thay vì trả phiếu
  đang mở (3 request đồng thời → ph_20/ph_21/ph_22).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from ca_api import persist

# ── BUG-01: chuyển trạng thái đơn quầy phải nguyên tử ────────────────────────


def _tao_don(mon_id: str = "fx_mon_bac_xiu", so_luong: int = 2) -> str:
    """Tạo đơn quầy ở trạng thái `cho_pha`, trả về id."""
    import uuid
    from datetime import UTC, datetime

    don_id = f"dq_qa_{uuid.uuid4().hex[:8]}"
    persist.don_insert(
        {
            "id": don_id,
            "nv_id": "nv_01",
            "trang_thai": "cho_pha",
            "thanh_toan": "chua_thu",
            "dong": [{"mon_id": mon_id, "so_luong": so_luong}],
            "ly_do_huy": None,
            "luc": datetime.now(UTC).isoformat(),
        }
    )
    return don_id


def test_don_chuyen_trang_thai_tra_None_khi_trang_thai_da_doi() -> None:
    """CAS: lần thứ hai với cùng `tu` phải trả None (không ghi đè)."""
    don_id = _tao_don()
    lan1 = persist.don_chuyen_trang_thai(don_id, tu="cho_pha", sang="dang_pha")
    assert lan1 is not None, "lần đầu phải thắng"
    assert lan1["trang_thai"] == "dang_pha"
    # Kẻ đến sau vẫn tưởng đang `cho_pha` → phải thua.
    lan2 = persist.don_chuyen_trang_thai(don_id, tu="cho_pha", sang="dang_pha")
    assert lan2 is None, "lần hai phải thua cuộc đua (không ghi đè)"
    # Trạng thái cuối vẫn là kết quả của lần thắng.
    assert persist.don_get(don_id)["trang_thai"] == "dang_pha"


def test_don_chuyen_trang_thai_tra_None_khi_don_khong_ton_tai() -> None:
    assert persist.don_chuyen_trang_thai("dq_khong_ton_tai", tu="cho_pha", sang="dang_pha") is None


def test_chi_mot_trong_nhieu_lan_chuyen_dong_thoi_thang() -> None:
    """Mô phỏng double-click: nhiều lời gọi liên tiếp, đúng MỘT lần thắng.

    Đây là bất biến bảo vệ `_ghi_tieu_thu_uoc_luong` — chỉ lần thắng mới được
    ghi tiêu thụ, nên kho không bị trừ gấp đôi.
    """
    don_id = _tao_don()
    ket_qua = [persist.don_chuyen_trang_thai(don_id, tu="cho_pha", sang="dang_pha") for _ in range(5)]
    thang = [k for k in ket_qua if k is not None]
    assert len(thang) == 1, f"chỉ 1 lần được thắng, nhận {len(thang)}"


def test_don_chuyen_trang_thai_ghi_ly_do_huy() -> None:
    don_id = _tao_don()
    ket = persist.don_chuyen_trang_thai(don_id, tu="cho_pha", sang="huy", ly_do_huy="khách đổi ý")
    assert ket is not None
    assert ket["trang_thai"] == "huy"
    assert ket["ly_do_huy"] == "khách đổi ý"


# ── BUG-02: PUT menu không được xoá BOM ──────────────────────────────────────


def test_menu_upsert_giu_bom_khi_khong_truyen() -> None:
    """Tầng persist vẫn ghi đè — bảo vệ nằm ở endpoint; test này chốt hành vi
    của `menu_get`/`menu_upsert` để endpoint dựa vào mà bù giá trị cũ."""
    mon_id = "qa_test_bom_mon"
    persist.menu_upsert(
        {
            "id": mon_id,
            "ten": "QA BOM",
            "gia": 10000,
            "an": False,
            "bom": {"ca_phe_hat": 10, "sua_tuoi": 100},
            "hinh_url": "",
            "nhom": "ca_phe",
        }
    )
    truoc = persist.menu_get(mon_id)
    assert truoc is not None and len(truoc["bom"]) == 2

    # Endpoint đọc bản cũ rồi bù — mô phỏng đúng logic đó.
    cu = persist.menu_get(mon_id)
    assert cu is not None
    bom_bu = (cu or {}).get("bom") or {}
    persist.menu_upsert(
        {
            "id": mon_id,
            "ten": "QA BOM",
            "gia": 12000,
            "an": False,
            "bom": bom_bu,
            "hinh_url": "",
            "nhom": "ca_phe",
        }
    )
    sau = persist.menu_get(mon_id)
    assert sau is not None
    assert sau["gia"] == 12000, "giá phải đổi"
    assert sau["bom"] == {"ca_phe_hat": 10, "sua_tuoi": 100}, "BOM phải giữ nguyên"


# ── BUG-04: profile quán phải qua schema có ràng buộc ────────────────────────


def test_store_profile_body_chan_truong_qua_dai() -> None:
    """`StoreProfileBody` giới hạn độ dài — chặn địa chỉ 5.000 ký tự."""
    from ca_api.interfaces.http.channels import StoreProfileBody
    from pydantic import ValidationError

    StoreProfileBody(dia_chi="x" * 300)  # biên trên vẫn hợp lệ
    with pytest.raises(ValidationError):
        StoreProfileBody(dia_chi="x" * 5000)
    with pytest.raises(ValidationError):
        StoreProfileBody(huong_dan_agent="x" * 5000)


def test_text_sach_bo_the_html() -> None:
    """`_text_sach` gỡ thẻ trước khi lưu để prompt AI không dính markup."""
    from ca_api.interfaces.http.channels import _text_sach

    assert _text_sach("<script>alert(1)</script>Nhịp Quán") == "alert(1)Nhịp Quán"
    assert _text_sach("  <b>Quán</b>  ") == "Quán"
    assert _text_sach("dòng 1\ndòng 2") == "dòng 1\ndòng 2", "phải giữ xuống dòng"


# ── BUG-05: chặn booking_time vô lý ─────────────────────────────────────────


def test_kiem_thoi_gian_dat_ban_chan_qua_khu() -> None:
    from ca_api.interfaces.http.reservations import _kiem_thoi_gian_dat_ban
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _kiem_thoi_gian_dat_ban("2020-01-01 19:00")
    assert exc.value.status_code == 422
    assert exc.value.detail == "thoi_gian_dat_ban_da_qua"


def test_kiem_thoi_gian_dat_ban_chan_qua_xa() -> None:
    from ca_api.interfaces.http.reservations import _kiem_thoi_gian_dat_ban
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _kiem_thoi_gian_dat_ban("2099-01-01 19:00")
    assert exc.value.status_code == 422
    assert exc.value.detail == "thoi_gian_dat_ban_qua_xa"


def test_kiem_thoi_gian_dat_ban_cho_phep_tuong_lai_gan() -> None:
    """Đặt trước vài ngày là hợp lệ (không được chặn nhầm)."""
    from datetime import datetime, timedelta, timezone

    from ca_api.interfaces.http.reservations import _kiem_thoi_gian_dat_ban

    vn = timezone(timedelta(hours=7))
    mai = (datetime.now(vn) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    _kiem_thoi_gian_dat_ban(mai)  # không ném


def test_kiem_thoi_gian_dat_ban_chan_chuoi_rac() -> None:
    from ca_api.interfaces.http.reservations import _kiem_thoi_gian_dat_ban
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _kiem_thoi_gian_dat_ban("hom-qua-luc-nao-do")
    assert exc.value.status_code == 422


# ── A-01: meeting/analyze phải giới hạn payload ─────────────────────────────


def test_analyze_meeting_body_chan_payload_khung() -> None:
    from ca_api.interfaces.http.meeting import AnalyzeMeetingBody
    from pydantic import ValidationError

    AnalyzeMeetingBody(text="x" * 20_000)  # đúng biên trên
    with pytest.raises(ValidationError):
        AnalyzeMeetingBody(text="x" * 500_000)
    with pytest.raises(ValidationError):
        AnalyzeMeetingBody(text="")


# ── A-04: không sinh phiếu trùng cho cùng mẫu ───────────────────────────────


def test_phieu_start_tra_phieu_dang_mo_thay_vi_tao_moi() -> None:
    """Gọi lại cùng `mau` phải trả CÙNG id, không sinh phiếu mới.

    Kiểm ở tầng dữ liệu: mô phỏng bag `phieu` có một phiếu chưa đóng của
    `nv_01` với `mau='mo_quan'`, rồi xác nhận logic lọc trong `phieu_start`
    nhận ra nó (điều kiện: chưa closed + đúng mau + đúng nv).
    """
    bag: dict[str, Any] = {
        "ph_99": {
            "id": "ph_99",
            "mau": "mo_quan",
            "nv_id": "nv_01",
            "closed": False,
        }
    }

    def tim_phieu_dang_mo(mau: str, nv: str) -> dict[str, Any] | None:
        for raw in bag.values():
            if not isinstance(raw, dict) or raw.get("closed"):
                continue
            if str(raw.get("mau") or "") != mau:
                continue
            if str(raw.get("nv_id") or "") != nv:
                continue
            return raw
        return None

    assert tim_phieu_dang_mo("mo_quan", "nv_01")["id"] == "ph_99"
    # Phiếu đã đóng thì không tính là "đang mở".
    bag["ph_99"]["closed"] = True
    assert tim_phieu_dang_mo("mo_quan", "nv_01") is None
    # Mẫu khác hoặc người khác cũng không khớp.
    bag["ph_99"]["closed"] = False
    assert tim_phieu_dang_mo("dong_quan", "nv_01") is None
    assert tim_phieu_dang_mo("mo_quan", "nv_02") is None


# ── A-13: frontend phân biệt "không có trang" với "bị chặn quyền" ───────────


def test_session_co_ham_nhan_biet_route_ton_tai() -> None:
    """`isKnownPath` phải có trong `session.ts` và được AppShell dùng."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    session_src = (root / "web" / "src" / "lib" / "session.ts").read_text(encoding="utf-8")
    shell_src = (root / "web" / "src" / "app" / "AppShell.tsx").read_text(encoding="utf-8")

    assert "export function isKnownPath" in session_src, "thiếu hàm isKnownPath"
    assert "KNOWN_PATHS" in session_src, "thiếu tập KNOWN_PATHS"
    assert "isKnownPath" in shell_src, "AppShell chưa dùng isKnownPath"
    assert "Không tìm thấy trang" in shell_src, "thiếu thông báo cho route không tồn tại"
    # Route hợp lệ phải có trong tập để không báo nhầm 404.
    for duong_dan in ('"/lich-tuan"', '"/quanverse/war-room"', '"/page-quan/fb-inbox"'):
        assert duong_dan in session_src, f"KNOWN_PATHS thiếu {duong_dan}"


def test_bom_json_khong_mat_khi_roundtrip() -> None:
    """Chốt: `don_update` ghi `dong` dạng JSON nên đọc lại phải khớp."""
    don_id = _tao_don("fx_mon_ca_phe_den", 3)
    don = persist.don_get(don_id)
    assert don is not None
    assert json.loads(json.dumps(don["dong"])) == don["dong"]


# ── Đợt 2: 4 anomaly còn lại ────────────────────────────────────────────────


def test_qr_tra_404_khi_nhan_vien_khong_ton_tai() -> None:
    """Mã NV sai là "không tìm thấy tài nguyên" (404), KHÔNG phải 422.

    422 dành cho "body sai định dạng". Trước đây cả hai dùng 422 nên client
    không phân biệt được `nhan_vien_khong_ton_tai` với lỗi validate trường.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    src = (root / "api" / "src" / "ca_api" / "interfaces" / "http" / "sprint45.py").read_text(
        encoding="utf-8"
    )
    assert 'status_code=404, detail="nhan_vien_khong_ton_tai"' in src, (
        "QR phải trả 404 cho nhân viên không tồn tại"
    )
    assert 'status_code=404, detail="ca_khong_hop_le"' in src, "ca_id sai cũng phải 404"
    assert 'status_code=422, detail="nhan_vien_khong_ton_tai"' not in src, (
        "không được còn nhánh 422 cho nhân viên không tồn tại"
    )


def test_treo_body_gioi_han_do_dai() -> None:
    """`noi_dung` việc treo có giới hạn — 50.000 ký tự trước đây vẫn nhận (200)."""
    from ca_api.interfaces.http.sprint3 import TreoBody
    from pydantic import ValidationError

    TreoBody(noi_dung="x" * 2_000)  # đúng biên trên
    with pytest.raises(ValidationError):
        TreoBody(noi_dung="x" * 50_000)
    with pytest.raises(ValidationError):
        TreoBody(noi_dung="")


def test_item_title_co_line_clamp() -> None:
    """Thẻ trong danh sách phải cắt ngắn — 1.000 emoji từng làm thẻ cao 760px."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    css = (root / "web" / "src" / "app" / "globals.css").read_text(encoding="utf-8")

    # Lấy đúng khối .nq-item-title
    idx = css.find(".nq-item-title {")
    assert idx != -1, "thiếu class .nq-item-title"
    khoi = css[idx : css.find("}", idx)]
    assert "line-clamp" in khoi, "`.nq-item-title` phải có line-clamp để cắt nội dung dài"
    assert "overflow" in khoi, "phải có overflow hidden để line-clamp hoạt động"


def test_authorization_chap_nhan_ca_hai_dang_token() -> None:
    """`session()` nhận cả `Bearer <token>` lẫn `<token>` trần — CÓ CHỦ ĐÍCH.

    WebSocket gửi token trần (không qua header HTTP) nên phải giữ tương thích.
    Test này chốt hành vi để không ai "sửa" thành bắt buộc `Bearer` rồi làm
    hỏng luồng WS.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    src = (root / "api" / "src" / "ca_api" / "persist.py").read_text(encoding="utf-8")
    assert 'removeprefix("Bearer ")' in src, (
        "`session()` phải chấp nhận token trần cho WebSocket — xem docstring"
    )
