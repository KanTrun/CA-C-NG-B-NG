# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Property: 8 consecutive weeks — max-debt spread does not explode."""

from __future__ import annotations

import pytest
from ca_solver import build_lich_input, solve_cpsat
from ca_solver.fairness import debt_spread

# Chậm (~4 phút: 8 lần solve CP-SAT) + nhạy tải CPU CI — chạy ở job unit-slow.
pytestmark = pytest.mark.slow


def test_fairness_eight_weeks_spread_bounded() -> None:
    data = build_lich_input()
    spreads: list[float] = []
    for _ in range(8):
        r = solve_cpsat(data, time_limit_s=30.0)
        assert r.ok, r.violations[:10]
        spreads.append(debt_spread(r.debt_after))
        data.debt = r.debt_after
    # Tuần 1 khởi đầu debt=0 nên spread thấp giả tạo — bỏ khỏi phép so.
    # Từ tuần 2 trở đi mọi người đã có debt nền: spread phải ỔN ĐỊNH, không
    # bùng nổ. Role-slot 91 lượt/tuần → mỗi người ~18h debt/tuần; spread
    # hội tụ quanh ~30. Bound: tuần cuối ≤ 2x trung bình W2..W7 + 15.
    steady = spreads[1:-1]
    avg_steady = sum(steady) / len(steady)
    assert spreads[-1] <= avg_steady * 2 + 15, spreads
    # Và spread không tăng đơn điệu suốt chuỗi (có tuần giảm trở lại).
    assert any(b < a for a, b in zip(spreads, spreads[1:], strict=False)), spreads
