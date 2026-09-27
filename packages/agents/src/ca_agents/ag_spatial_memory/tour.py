"""Tour planner — chuỗi anchor đóng, narration grounded (không LLM thêm fact)."""

from __future__ import annotations

from ca_contracts import (
    ExperienceMemory,
    TourPlan,
    TourStep,
)

# Route mở quán mặc định (deterministic, closed graph)
OPENING_ROUTE = [
    ("entrance", "Cửa vào — nơi đón khách đầu tiên"),
    ("bar", "Quầy pha chế — trái tim đồ uống"),
    ("cashier", "Quầy thu ngân — thanh toán và hỗ trợ"),
    ("espresso-machine-01", "Máy pha cà phê chính"),
    ("window_table", "Bàn cửa sổ — khu vực khách ngồi"),
]

# Danh mục tour đóng (deterministic). Endpoint nhận `{tour_id}` nên phải tra
# đúng mã; mã lạ phải trả 404 thay vì lặng lẽ trả tour mặc định (bug QA đợt 4:
# mọi tour_id — kể cả "khong-ton-tai" — đều trả tour_chao_doi).
_MAC_DINH = "tour_chao_doi"
_TOURS: dict[str, list[tuple[str, str]]] = {
    _MAC_DINH: OPENING_ROUTE,
    "tour_dong_quan": [
        ("bar", "Quầy pha chế — vệ sinh và kiểm kê cuối ca"),
        ("cashier", "Quầy thu ngân — chốt doanh thu trong ngày"),
        ("window_table", "Bàn cửa sổ — dọn khu vực khách"),
        ("entrance", "Cửa vào — tắt biển và khoá cửa"),
    ],
    "tour_kho": [
        ("storage", "Kho nguyên liệu — kiểm tồn theo mã hàng"),
        ("bar", "Quầy pha chế — đối chiếu tiêu thụ với tồn"),
        ("espresso-machine-01", "Máy pha cà phê — chuẩn lượng hạt mỗi ly"),
    ],
}


def danh_muc_tour() -> list[str]:
    """Danh sách mã tour hợp lệ (để tầng API trả 404 đúng cho mã lạ)."""
    return sorted(_TOURS)


def plan_tour(
    route: list[tuple[str, str]] | None = None,
    memories: list[ExperienceMemory] | None = None,
    *,
    tour_id: str | None = None,
) -> TourPlan | None:
    """Dựng tour từ route đóng + memory confirmed để narration grounded.

    Nếu một step thiếu memory confirmed thì narration vẫn dùng mô tả anchor
    (không bịa sự kiện) và citation rỗng.

    Trả ``None`` khi ``tour_id`` được truyền nhưng không có trong danh mục —
    để tầng API trả 404 thay vì trả tour mặc định.
    """
    if route is not None:
        ten_tour = tour_id if tour_id else _MAC_DINH
        cac_buoc = route
    else:
        # Phân biệt `None` (không truyền → dùng mặc định) với chuỗi rỗng
        # (truyền nhưng rỗng → không hợp lệ → None → API trả 404).
        if tour_id is None:
            ten_tour = _MAC_DINH
        elif tour_id == "" or tour_id not in _TOURS:
            return None
        else:
            ten_tour = tour_id
        cac_buoc = _TOURS[ten_tour]

    steps: list[TourStep] = []
    confirmed = [m for m in (memories or []) if m.status.value == "confirmed"]
    for idx, (anchor_id, desc) in enumerate(cac_buoc, start=1):
        related = [m for m in confirmed if m.anchor_id == anchor_id]
        citation_ids = [m.memory_id for m in related[:3]]
        narrative = desc
        if related:
            extra = "; ".join(m.content for m in related[:2])
            narrative = f"{desc}. Ký ức: {extra}"
        steps.append(
            TourStep(
                step_id=f"step_{idx:02d}",
                anchor_id=anchor_id,
                narrative=narrative,
                citation_memory_ids=citation_ids,
            )
        )
    return TourPlan(tour_id=ten_tour, steps=steps, grounded=True)