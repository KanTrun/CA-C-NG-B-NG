# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Test tour planner — mã tour phải được tôn trọng, mã lạ trả None (→ 404).

Bug QA đợt 4 (2026-09-26): `GET /api/v1/experience/quanverse/tour/{tour_id}` bỏ
qua tham số `tour_id` và luôn trả tour mặc định `tour_chao_doi` — kể cả với mã
không tồn tại như "khong-ton-tai". Test này khoá hành vi đúng.
"""

from __future__ import annotations

from ca_agents.ag_spatial_memory.tour import (
    OPENING_ROUTE,
    danh_muc_tour,
    plan_tour,
)


def test_tour_mac_dinh_khi_khong_truyen_id() -> None:
    tour = plan_tour()
    assert tour is not None
    assert tour.tour_id == "tour_chao_doi"


def test_tour_dung_ma_duoc_yeu_cau() -> None:
    tour = plan_tour(tour_id="tour_chao_doi")
    assert tour is not None
    assert tour.tour_id == "tour_chao_doi"
    assert len(tour.steps) == len(OPENING_ROUTE)


def test_tour_khac_ma_cho_noi_dung_khac() -> None:
    a = plan_tour(tour_id="tour_chao_doi")
    b = plan_tour(tour_id="tour_dong_quan")
    assert a is not None and b is not None
    assert a.tour_id != b.tour_id
    assert [s.anchor_id for s in a.steps] != [s.anchor_id for s in b.steps]


def test_ma_tour_khong_ton_tai_tra_none() -> None:
    """Đây là bug đã sửa: trước đây trả tour mặc định thay vì None."""
    assert plan_tour(tour_id="khong-ton-tai") is None
    assert plan_tour(tour_id="") is None


def test_danh_muc_tour_liet_ke_ma_hop_le() -> None:
    ds = danh_muc_tour()
    assert "tour_chao_doi" in ds
    assert "tour_dong_quan" in ds
    assert ds == sorted(ds)


def test_route_tuy_chinh_van_dung() -> None:
    """Truyền route riêng → dùng route đó, không tra danh mục."""
    tour = plan_tour(route=[("bar", "Chỉ quầy bar")], tour_id="tour_tuy_chinh")
    assert tour is not None
    assert tour.tour_id == "tour_tuy_chinh"
    assert len(tour.steps) == 1
    assert tour.steps[0].anchor_id == "bar"
