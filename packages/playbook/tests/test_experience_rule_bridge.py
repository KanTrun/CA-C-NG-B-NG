"""Bridge test — RuleCandidate (Phase 04) nối vào playbook vong_doi 8-step.

Vong_doi là SOLE WRITER cho trạng thái luật. Candidate của experience chỉ
đóng gói evidence → de_xuat → kiem_chung → tap_su → duyet (bước 3-8).
Không có state machine luật thứ hai.
"""

from __future__ import annotations

from ca_agents.ag_rule_learning.discover import (
    DecisionSignal,
    discover_rule_candidates,
    to_vf_condition,
)
from ca_contracts import RuleCandidate
from ca_playbook.vong_doi import de_xuat, kiem_chung

SNAP = "snap_bridge_20260918"


def _candidate() -> RuleCandidate:
    sigs = [
        DecisionSignal(signal_id="e1", decision="them_nguoi_gio_cao", outcome="ok", day_part="toi", station="bar", skill="pha_che", demand_band="cao"),
        DecisionSignal(signal_id="e2", decision="them_nguoi_gio_cao", outcome="ok", day_part="toi", station="bar", skill="pha_che", demand_band="cao"),
        DecisionSignal(signal_id="e3", decision="them_nguoi_gio_cao", outcome="ok", day_part="toi", station="bar", skill="pha_che", demand_band="cao"),
    ]
    cands = discover_rule_candidates(sigs, snapshot_hash=SNAP)
    return cands[0]


def test_candidate_bridges_to_vong_doi() -> None:
    cand = _candidate()
    mau = {
        "mau": "them_nguoi_gio_cao",
        "loai_luat": "nhu_cau_ca",
        "n": len(cand.evidence_refs),
        "bang_chung": cand.evidence_refs,
        "nguon": "fixture_replay",
    }
    # Bridge: condition experience → VF-RULE fields (khung/vi_tri/so_nguoi)
    vf_cond = to_vf_condition(cand.condition)
    luat = de_xuat(
        mau,
        ban_nhap={"cau": cand.sentence, "dieu_kien": vf_cond, "bang_chung": cand.evidence_refs},
    )
    assert luat is not None
    assert luat["trang_thai"] == "de_xuat"
    assert luat["buoc"] == 3

    verified = kiem_chung(luat)
    assert verified["buoc"] >= 4
    # VF-RULE phải pass với fields đã map (không còn "loai")
    assert verified["trang_thai"] == "qua_vf_rule"


def test_insufficient_evidence_no_rule() -> None:
    """2 tín hiệu (dưới ngưỡng 3) → không candidate → de_xuat trả None."""
    sigs = [
        DecisionSignal(signal_id="e1", decision="x", outcome="ok"),
        DecisionSignal(signal_id="e2", decision="x", outcome="ok"),
    ]
    cands = discover_rule_candidates(sigs, snapshot_hash=SNAP)
    assert cands == []
    luat = de_xuat(
        {"mau": "x", "loai_luat": "khac", "n": 2, "bang_chung": ["e1", "e2"], "nguon": "replay"},
        ban_nhap=None,
    )
    assert luat is None  # không bịa luật


def test_conflicting_outcome_stays_needs_review() -> None:
    """Counterexample → candidate vẫn chờ review, không tự duyệt."""
    sigs = [
        DecisionSignal(signal_id="e1", decision="x", outcome="ok"),
        DecisionSignal(signal_id="e2", decision="x", outcome="ok"),
        DecisionSignal(signal_id="e3", decision="x", outcome="reject"),
    ]
    cands = discover_rule_candidates(sigs, snapshot_hash=SNAP)
    assert len(cands) == 1
    assert cands[0].counterexample_refs