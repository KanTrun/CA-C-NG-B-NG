# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest
from ca_api.interfaces.http.main import app
from ca_api.persist import kv_get, kv_set
from fastapi.testclient import TestClient

from unit.auth_util import headers

ROOT = Path(__file__).resolve().parents[4]

client = TestClient(app)
PHOTO = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="


def _hom_nay() -> str:
    return datetime.now(timezone(timedelta(hours=7))).date().isoformat()


def test_diem_danh_tuong_thich_nguoc_du_lieu_list_cu() -> None:
    """KV `diem_danh` bản cũ là list nv_id; write path phải migrate chứ không 500.

    Regression: `mut()` gọi `.get()` trên list → AttributeError → 500 → UI báo
    "Không ghi được điểm danh" và không render nút Mở quán.
    """
    kv_set("diem_danh", ["nv_09"])
    auth = headers(client, "minh")

    r = client.post("/api/v1/diem-danh", headers=auth)

    assert r.status_code == 200, r.text
    assert r.json()["nv_id"] == "nv_03"
    luu = kv_get("diem_danh", {})
    assert isinstance(luu, dict)
    # nv cũ được giữ (đọc như check-in hôm nay) và nv mới được thêm vào.
    assert set(luu[_hom_nay()]) == {"nv_09", "nv_03"}


def test_diem_danh_khong_loi_khi_kv_hong() -> None:
    """KV sai kiểu (không phải list/dict) vẫn ghi được, không 500."""
    kv_set("diem_danh", "chuoi_khong_hop_le")
    auth = headers(client, "minh")

    r = client.post("/api/v1/diem-danh", headers=auth)

    assert r.status_code == 200, r.text
    assert kv_get("diem_danh", {})[_hom_nay()] == ["nv_03"]


def test_phieu_twenty_steps_and_treo() -> None:
    auth = headers(client, "minh")
    client.post("/api/v1/diem-danh", headers=auth)
    r = client.post("/api/v1/phieu/start", json={"mau": "mo_quan"}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["so_buoc"] >= 20
    pid = body["id"]
    for b in body["buocs"]:
        if b["loai"] == "photo":
            rr = client.post(
                f"/api/v1/phieu/{pid}/minh-chung",
                json={"buoc_ma": b["ma"], "data_url": PHOTO},
                headers=auth,
            )
        else:
            rr = client.post(
                f"/api/v1/phieu/{pid}/buoc",
                json={"ma": b["ma"], "gia_tri": "4" if b["loai"] == "text" else "ok"},
                headers=auth,
            )
        assert rr.status_code == 200, rr.text
        body = rr.json()
    assert body["trang_thai"] == "hoan_thanh"
    timing = body["signals"]["timing_ms"]
    assert isinstance(timing, dict)
    assert timing
    assert all(isinstance(k, str) for k in timing)
    tr = client.post(
        f"/api/v1/phieu/{pid}/treo",
        json={"noi_dung": "hết đá"},
        headers=auth,
    )
    assert tr.status_code == 200
    hung = client.get("/api/v1/viec-treo", headers=auth).json()["items"]
    assert any("đá" in x["noi_dung"] for x in hung)


def test_photo_rejected_without_payload() -> None:
    auth = headers(client, "minh")
    client.post("/api/v1/diem-danh", headers=auth)
    r = client.post("/api/v1/phieu/start", json={"mau": "mo_quan"}, headers=auth)
    pid = r.json()["id"]
    first_photo = next(b for b in r.json()["buocs"] if b["loai"] == "photo")
    for b in r.json()["buocs"]:
        if b["ma"] == first_photo["ma"]:
            break
        client.post(
            f"/api/v1/phieu/{pid}/buoc",
            json={"ma": b["ma"], "gia_tri": "4"},
            headers=auth,
        )
    bad = client.post(
        f"/api/v1/phieu/{pid}/minh-chung",
        json={"buoc_ma": first_photo["ma"], "data_url": ""},
        headers=auth,
    )
    assert bad.status_code == 400


def test_start_requires_diem_danh() -> None:
    chu = headers(client, "hung")
    r = client.post("/api/v1/phieu/start", json={"mau": "mo_quan"}, headers=chu)
    assert r.status_code == 403


def test_ban_giao_ca_khong_can_diem_danh() -> None:
    chu = headers(client, "hung")
    r = client.post("/api/v1/phieu/start", json={"mau": "ban_giao_ca"}, headers=chu)
    assert r.status_code == 200, r.text


def test_mau_phieu_tat_khong_hien_va_khong_mo_duoc(monkeypatch, tmp_path: Path) -> None:
    cfg = tmp_path / "quy-trinh-phieu.yaml"
    cfg.write_text(
        "mac_dinh:\n  - ma: mo_quan\n    bat: false\n  - ma: ban_giao_ca\n    bat: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NHIPQUAN_PHIEU_CONFIG", str(cfg))
    auth = headers(client, "minh")

    listed = client.get("/api/v1/phieu/mau", headers=auth)
    assert listed.status_code == 200
    assert [item["ma"] for item in listed.json()["items"]] == ["ban_giao_ca"]
    denied = client.post("/api/v1/phieu/start", json={"mau": "mo_quan"}, headers=auth)
    assert denied.status_code == 404


def test_mau_phieu_theo_tung_quan(monkeypatch, tmp_path: Path) -> None:
    cfg = tmp_path / "quy-trinh-phieu.yaml"
    cfg.write_text(
        "mac_dinh:\n  - ma: mo_quan\n    bat: true\n"
        "quan:\n  quan_02:\n    - ma: ban_giao_ca\n      bat: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NHIPQUAN_PHIEU_CONFIG", str(cfg))
    monkeypatch.setattr(
        "ca_api.interfaces.http.sprint3.auth_session",
        lambda _: {"nv_id": "nv_03", "role": "nhan_vien", "store_id": "quan_02"},
    )

    listed = client.get("/api/v1/phieu/mau", headers={"Authorization": "Bearer test"})
    assert listed.status_code == 200
    assert [item["ma"] for item in listed.json()["items"]] == ["ban_giao_ca"]


def test_orc_idempotency() -> None:
    ql = headers(client, "lan")
    a = client.post("/api/v1/orc/dispatch", json={"n": 8, "key": "k-test"}, headers=ql).json()
    b = client.post("/api/v1/orc/dispatch", json={"n": 8, "key": "k-test"}, headers=ql).json()
    assert a["n"] == 8
    assert a["writes"] == 8
    assert a["replayed"] is False
    assert b["replayed"] is True
    assert b["writes"] == 8


def test_ghi_nhan_after_nha() -> None:
    from ca_api.interfaces.http.sprint3 import _current_week, _phan_cong

    phan = dict(_phan_cong())
    if "nv_03" in phan.get("w1_c01", []):
        phan["w1_c01"] = [x for x in phan["w1_c01"] if x != "nv_03"]
        kv_set("phan_cong", phan)
    # Nhả ca chỉ hợp lệ khi lịch đã công bố (cổng `lich_chua_cong_bo`), nên bài
    # này phải dựng tuần hiện tại ở trạng thái đã công bố trước khi thao tác.
    week = _current_week()
    kv_set("lich_tuan_lifecycle_by_week", {week: {"tuan_iso": week, "trang_thai": "da_cong_bo"}})
    kv_set("lich_tuan_lifecycle", {"tuan_iso": week, "trang_thai": "da_cong_bo"})

    auth = headers(client, "minh")
    # Nhận ca trực tiếp là đường của QUẢN LÝ (`ca/nhan` giờ trỏ sang chợ đổi ca).
    quan_ly = headers(client, "lan")
    nhan = client.post(
        "/api/v1/ca/nhan-truc-tiep", json={"ca_id": "w1_c01", "nv_id": "nv_03"}, headers=quan_ly
    )
    assert nhan.status_code == 200, nhan.text
    assert nhan.json()["truoc"] != nhan.json()["sau"]
    nha = client.post("/api/v1/ca/nha", json={"ca_id": "w1_c01"}, headers=auth)
    assert nha.status_code == 200, nha.text
    assert "nv_03" in nha.json()["truoc"]
    assert "nv_03" not in nha.json()["sau"]
    items = client.get("/api/v1/ghi-nhan-sua", headers=auth).json()["items"]
    assert items
    last = items[-1]
    assert "truoc" in last and "sau" in last
    assert last["truoc"] != last["sau"]


def test_phieu_seq_unique_under_parallel() -> None:
    """`phieu_seq` phải cấp id duy nhất kể cả khi nhiều request cùng lúc.

    Cập nhật theo hành vi mới (QA đợt 5): `phieu_start` trả **phiếu đang mở**
    cùng mẫu của chính mình thay vì tạo phiếu mới mỗi lần. Nên 8 request song
    song CÙNG mẫu giờ trả về **một** id — đó là điều mong muốn (trước đây sinh
    `ph_20`/`ph_21`/`ph_22` song song, mỗi bước ghi rải rác nên không phiếu nào
    đủ bước).

    Bất biến gốc vẫn phải giữ: **không hai phiếu nào trùng id**. Kiểm bằng cách
    mở nhiều MẪU KHÁC NHAU song song — mỗi mẫu phải ra id riêng.
    """
    from concurrent.futures import ThreadPoolExecutor

    auth = headers(client, "minh")
    client.post("/api/v1/diem-danh", headers=auth)

    # 1. Cùng mẫu song song → phải hội tụ về MỘT phiếu (không sinh trùng).
    def start_cung_mau() -> str:
        r = client.post("/api/v1/phieu/start", json={"mau": "mo_quan"}, headers=auth)
        assert r.status_code == 200, r.text
        return cast(str, r.json()["id"])

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids_cung_mau = list(pool.map(lambda _: start_cung_mau(), range(8)))
    assert len(set(ids_cung_mau)) == 1, (
        f"cùng mẫu phải trả về đúng 1 phiếu đang mở, nhận {len(set(ids_cung_mau))} id khác nhau"
    )

    # 2. Danh sách mẫu khác nhau chạy song song → id phải DUY NHẤT.
    mau_list = [entry["ma"] for entry in client.get("/api/v1/phieu/mau", headers=auth).json()["items"]]

    def start_mau(mau: str) -> str:
        r = client.post("/api/v1/phieu/start", json={"mau": mau}, headers=auth)
        assert r.status_code == 200, r.text
        return cast(str, r.json()["id"])

    with ThreadPoolExecutor(max_workers=max(2, len(mau_list))) as pool:
        ids = list(pool.map(start_mau, mau_list))
    assert len(ids) == len(set(ids)), f"id phiếu bị trùng: {ids}"


def test_phan_cong_doc_lich_tuan_theo_tmp_path_cua_test(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`_phan_cong()` phải đọc lịch tuần từ ĐƯỜNG DẪN CỦA BÀI TEST, không phải file thật.

    Vì sao có bài này: `_lich_out()` từng chốt đường dẫn ở CẤP MODULE
    (`LICH = ROOT / "data" / "out" / "lich_tuan.json"`), nên `NHIPQUAN_LICH_TUAN_OUT`
    mà conftest set theo từng bài **không bao giờ được thấy**. Test đọc thẳng vào
    file thật của quán.

    Hậu quả thật: `_phan_cong()` ưu tiên file lịch tuần hơn seed. Một file sót lại từ
    lần chạy demo trước đã che seed vĩnh viễn — file thật có `w1_c01 = ['nv_03','nv_38']`
    còn seed nói `['nv_07','nv_19']`. Nên `test_ghi_nhan_after_nha` nhận `nv_03` đã ở
    trong ca và trả **409 `da_trong_ca`**, đỏ trên mọi máy có file đó.

    Bài này chốt lại hợp đồng: file lịch tuần giả do bài test đặt PHẢI được đọc, và
    file thật KHÔNG được đụng tới.
    """
    from ca_api.interfaces.http import sprint3

    fake = tmp_path / "lich_tuan.json"
    fake.write_text(
        json.dumps({"phan_cong": {"ca_gia": ["nv_gia_01"]}}), encoding="utf-8"
    )
    monkeypatch.setenv("NHIPQUAN_LICH_TUAN_OUT", str(fake))
    # Bỏ kv để `_phan_cong()` rơi xuống nhánh đọc file.
    kv_set("phan_cong", None)

    assert sprint3._lich_out() == fake, (
        "_lich_out() khong doc NHIPQUAN_LICH_TUAN_OUT — duong dan dang bi chot o cap module"
    )
    assert sprint3._phan_cong() == {"ca_gia": ["nv_gia_01"]}, (
        "_phan_cong() khong doc file lich tuan cua bai test"
    )
    # Và file THẬT của quán không được đụng tới.
    that = ROOT / "data" / "out" / "lich_tuan.json"
    if that.exists():
        assert "ca_gia" not in that.read_text(encoding="utf-8"), (
            "bai test da ghi vao file lich tuan THAT cua quan"
        )
