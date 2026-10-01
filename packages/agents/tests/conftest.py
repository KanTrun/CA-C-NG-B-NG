"""Shared deterministic defaults for the agents test suite."""

from __future__ import annotations

import os

import pytest


def pytest_configure() -> None:
    """Đăng ký hypothesis profile 'ci' khi chạy trên CI.

    Import lười bên trong hook (không ở đầu module) để mypy/reviewdog không
    gắn cờ import thiếu khi môi trường không cài hypothesis, và local dev
    không có hypothesis vẫn chạy bình thường.
    """
    try:
        from hypothesis import HealthCheck, Verbosity, settings
    except ImportError:
        return
    # Profile CI: hypothesis ~5000 examples → ~50. Đủ bắt bất biến, không đốt
    # 10 phút runner. Local dev giữ nguyên số mẫu đầy đủ.
    settings.register_profile(
        "ci",
        max_examples=50,
        derandomize=True,
        deadline=None,
        verbosity=Verbosity.quiet,
        suppress_health_check=list(HealthCheck),
    )
    if os.environ.get("CI") == "true":
        settings.load_profile("ci")


@pytest.fixture(autouse=True)
def _default_to_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent a developer's live .env from changing test behavior."""
    monkeypatch.setenv("CA_AGENT_MODE", "replay")
    monkeypatch.setenv("NHIPQUAN_AUTO_RESERVATION", "1")
    # 20s (không phải 4s): CP-SAT bật 8 luồng, còn pytest chạy `-n auto` — tranh
    # CPU làm 4 giây không đủ tìm nghiệm đầu tiên, trả `UNKNOWN` và làm test solver
    # đỏ ngẫu nhiên. Xem `apps/api/tests/conftest.py` để biết đầy đủ.
    monkeypatch.setenv("CA_SOLVER_TIME_LIMIT_S", "20.0")
    # Jev phải tắt trong test — không gọi API thật (mạng/key/phí).
    monkeypatch.delenv("JEV_ENABLED", raising=False)
    monkeypatch.delenv("JEV_API_KEY", raising=False)

    import ca_agents.ag_concierge as concierge_mod

    monkeypatch.setattr(
        concierge_mod,
        "_RESERVATION_BACKEND",
        {
            "book": lambda **kwargs: {
                "id": "res_test_mock",
                "table_ids": ["B105"],
                "status": "confirmed",
                "booking_time": kwargs.get("booking_time"),
                "party_size": kwargs.get("party_size"),
                "dialog_step": "CONFIRMED",
            },
            "anti_abuse": lambda **kwargs: (True, None),
            "cancel": lambda *args: True,
            "notify": lambda *args: None,
            "is_enabled": lambda: True,
        },
    )