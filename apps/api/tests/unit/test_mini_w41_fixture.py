"""Fixture 4 NV + W41: xếp/journal/swap tái lập được trong vài phút."""

from __future__ import annotations

from ca_api.interfaces.http.main import app
from ca_api.persist import kv_get, kv_set
from ca_api.services.mini_w41_fixture import (
    MINI_W41_WEEK,
    publish_mini_w41_for_swap,
    seed_mini_w41_roster,
)
from ca_api.services.solver_adapter import ghi_nhat_ky_thay_doi
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)


def test_seed_mini_w41_co_4_nv_va_phan_cong_mau() -> None:
    seeded = seed_mini_w41_roster()
    assert seeded["ok"] is True
    assert seeded["tuan_iso"] == MINI_W41_WEEK
    assert len(seeded["nv_ids"]) >= 4
    assert "nv_01" in seeded["phan_cong"]["w1_c01"]
    life = kv_get("lich_tuan_lifecycle_by_week", {})[MINI_W41_WEEK]
    assert life["trang_thai"] == "nhap"


def test_api_demo_mini_w41_chi_quan_ly() -> None:
    nv = headers(client, "minh")
    assert client.post("/api/v1/lich-tuan/demo-mini-w41", headers=nv).status_code == 403
    ql = headers(client, "lan")
    r = client.post("/api/v1/lich-tuan/demo-mini-w41", headers=ql)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tuan_iso"] == MINI_W41_WEEK
    assert body["huong_dan"]


def test_mini_w41_xep_journal_roi_swap_thay_a_sang_b() -> None:
    """Checklist hẹp: seed → ghi nhật ký xếp → công bố → duyệt swap → nhật ký doi_ca."""
    seeded = seed_mini_w41_roster()
    week = seeded["tuan_iso"]
    ca_id = "w1_c01"

    # Giả lập một lần xếp tự động ghi nhật ký (A vào ca — nguồn xep_tu_dong).
    ban = ghi_nhat_ky_thay_doi(
        week,
        seeded["phan_cong"],
        nguon="xep_tu_dong",
        truoc={},
    )
    assert ban is not None
    assert ban["nguon"] == "xep_tu_dong"

    publish_mini_w41_for_swap()
    kv_set("phan_cong", dict(seeded["phan_cong"]))
    kv_set("phan_cong_by_week", {week: dict(seeded["phan_cong"])})

    opened = client.post(
        "/api/v1/cho-doi-ca",
        json={"a": "nv_01", "b": "nv_03", "ca_id": ca_id},
        headers=headers(client, "lan"),
    ).json()

    from ca_api.persist import kv_mutate

    def mut_tuan(items):
        for it in items:
            if it.get("id") == opened["id"]:
                it["tuan_id"] = week
        return items

    kv_mutate("swap", mut_tuan, [])

    # NV nhận đồng ý (có thể bị cổng quản lý — trạng thái vẫn dong_y).
    client.post(
        f"/api/v1/cho-doi-ca/{opened['id']}/dong-y",
        headers=headers(client, "minh"),
    )
    duyet = client.post(
        f"/api/v1/cho-doi-ca/{opened['id']}/duyet",
        headers=headers(client, "lan"),
    )
    assert duyet.status_code == 200, duyet.text

    journal = kv_get("lich_thay_doi_by_week", {}).get(week) or []
    assert any(b.get("nguon") == "xep_tu_dong" for b in journal)
    doi_ca = [b for b in journal if b.get("nguon") == "doi_ca"]
    assert doi_ca, journal
    hoan = doi_ca[-1]["diff"]["hoan_doi"]
    assert hoan
    ra = {r["nv_id"] for r in hoan[0]["ra"]}
    vao = {v["nv_id"] for v in hoan[0]["vao"]}
    assert "nv_01" in ra
    assert "nv_03" in vao

    # API nhật ký đọc được theo tuần W41.
    api = client.get(
        f"/api/v1/lich-tuan/thay-doi?tuan_iso={week}",
        headers=headers(client, "lan"),
    )
    assert api.status_code == 200
    assert api.json()["so_ban_ghi"] >= 2
