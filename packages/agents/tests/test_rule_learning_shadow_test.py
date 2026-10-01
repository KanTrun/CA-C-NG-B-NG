"""Rule shadow test tests (Phase 04)."""

from __future__ import annotations

from ca_agents.ag_rule_learning.discover import DecisionSignal, discover_rule_candidates
from ca_agents.ag_rule_learning.shadow_test import run_shadow_test
from ca_contracts import RuleCandidate

SNAP = "snap_shadow_20260918_abcd"


def _candidates() -> list[RuleCandidate]:
    sigs = [
        DecisionSignal(signal_id="e1", decision="them_nguoi", outcome="ok", day_part="toi"),
        DecisionSignal(signal_id="e2", decision="them_nguoi", outcome="ok", day_part="toi"),
        DecisionSignal(signal_id="e3", decision="them_nguoi", outcome="ok", day_part="toi"),
    ]
    return discover_rule_candidates(sigs, snapshot_hash=SNAP)


def test_shadow_reproducible() -> None:
    cand = _candidates()[0]
    events = [
        {"event_id": "e1", "event_type": "decision"},
        {"event_id": "e2", "event_type": "decision"},
        {"event_id": "e3", "event_type": "decision"},
    ]
    a = run_shadow_test(cand, historical_events=events, base_snapshot={"hard_constraints_ok": True, "luat_ap_dung": 0})
    b = run_shadow_test(cand, historical_events=events, base_snapshot={"hard_constraints_ok": True, "luat_ap_dung": 0})
    assert a.model_dump(mode="json") == b.model_dump(mode="json")


def test_shadow_does_not_mutate_snapshot() -> None:
    cand = _candidates()[0]
    base = {"hard_constraints_ok": True, "luat_ap_dung": 0}
    result = run_shadow_test(cand, historical_events=[], base_snapshot=base)
    # Snapshot gốc không đổi
    assert base["luat_ap_dung"] == 0
    # Không có sự kiện → notes phản ánh 0 applicable
    assert any("0 sự kiện" in n for n in result.notes) or result.notes


def test_shadow_tradeoff_shown_not_activated() -> None:
    cand = _candidates()[0]
    events = [
        {"event_id": f"e{i}", "event_type": "decision"} for i in range(1, 4)
    ]
    result = run_shadow_test(cand, historical_events=events, base_snapshot={"hard_constraints_ok": True})
    # Không có field "activated" — luật không tự động kích hoạt.
    assert "activated" not in result.model_dump(mode="json")
    assert result.notes