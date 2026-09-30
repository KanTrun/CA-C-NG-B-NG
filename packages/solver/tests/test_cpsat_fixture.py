# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""CP-SAT smoke on fixture."""

from __future__ import annotations

import pytest
from ca_solver import build_lich_input, solve_cpsat, solve_hard_only

# Chậm (~2 phút: 2 lần solve 60s) — chạy ở job unit-slow.
pytestmark = pytest.mark.slow


def test_cpsat_fixture_zero_hard() -> None:
    data = build_lich_input()
    r = solve_cpsat(data, time_limit_s=60.0)
    assert r.status in {"OPTIMAL", "FEASIBLE"}, r.status
    # Allow margin for model building overhead (solver uses time_limit_s - 0.5 internally)
    assert r.elapsed_s < 65.0
    check = solve_hard_only(
        type(data)(
            **{
                **data.__dict__,
                "phan_cong": r.phan_cong,
            }
        )
    )
    assert check.ok, check.violations


def test_cpsat_enforces_pinned_shift() -> None:
    data = build_lich_input()
    # w1_c02 là role-slot thu_ngan T2 sáng; nv_02 biết thu_ngan, rảnh T2 sáng.
    data.phan_cong["w1_c02"] = ["nv_02"]
    r = solve_cpsat(data, time_limit_s=60.0)
    assert r.ok is True
    assert "nv_02" in r.phan_cong["w1_c02"]

