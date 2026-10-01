"""Brief Quánverse gắn tín hiệu AI FORECAST thời tiết."""

from __future__ import annotations

from ca_agents.ag_quanverse.brief import brief_living_map
from ca_contracts import QuanversePage


def _base_zones() -> list[dict]:
    return [
        {"zone_id": "bar", "label": "Quầy bar", "load_signal": 0.3, "active": True},
        {"zone_id": "ngoai", "label": "Ngoài trời", "load_signal": 0.5, "active": True},
    ]


def test_brief_khong_co_thoi_tiet_van_chay() -> None:
    facts = brief_living_map(
        zones=_base_zones(),
        events=[],
        modes=[],
        horizon=[],
        thoi_tiet=None,
    )
    assert facts.page == QuanversePage.LIVING_MAP
    assert not any("Thời tiết" in f for f in facts.facts)


def test_brief_mua_de_xuat_troi_mua() -> None:
    facts = brief_living_map(
        zones=_base_zones(),
        events=[],
        modes=[],
        horizon=[],
        thoi_tiet={
            "co_du_lieu": True,
            "vi_tri": {"thanh_pho": "Quận 1", "tinh": "Hồ Chí Minh"},
            "hien_tai": {"mo_ta": "Mưa to", "nhiet_do": 26.0, "nhom": "mua_to"},
            "anh_huong_quan": {
                "tom_tat": "Mưa to: dồn chỗ trong nhà, ưu tiên món nóng.",
                "yeu_to": ["Khách khu ngoài trời giảm mạnh."],
                "de_xuat_mode": "troi_mua",
                "de_xuat_mode_label": "Trời mưa",
            },
        },
    )
    assert any("Thời tiết hiện tại" in f for f in facts.facts)
    assert any("Mưa to" in r for r in facts.risks)
    assert any("Trời mưa" in a for a in facts.next_actions)
    assert "thoi_tiet_hom_nay" in facts.grounded_refs
    assert "de_xuat_mode:troi_mua" in facts.grounded_refs


def test_brief_thieu_dia_chi_data_quality() -> None:
    facts = brief_living_map(
        zones=_base_zones(),
        events=[],
        modes=[],
        horizon=[],
        thoi_tiet={"co_du_lieu": False, "can_cau_hinh": True},
    )
    codes = [dq.code for dq in facts.data_quality]
    assert "thoi_tiet_thieu_dia_chi" in codes
    assert any("vị trí" in dq.message.lower() or "gps" in dq.message.lower() for dq in facts.data_quality)
