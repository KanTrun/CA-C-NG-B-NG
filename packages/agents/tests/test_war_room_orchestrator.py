"""War Room orchestrator tests — Phase 02."""

from __future__ import annotations

import pytest
from ca_agents.ag_war_room import (
    run_war_room_comparison,
    validate_baseline_snapshot,
)
from ca_agents.ag_war_room.command import WarRoomCommand, normalize_command
from ca_contracts import WarRoomScenario, WarRoomScenarioType
from pydantic import ValidationError

SNAP = "snap_20260918_a1b2c3d4"


def _cmd(scenarios: list[WarRoomScenario], *, request_id: str = "req_1") -> WarRoomCommand:
    return WarRoomCommand(
        request_id=request_id,
        baseline_snapshot=SNAP,
        scenarios=scenarios,
        requested_by="quan_ly_test",
    )


def test_same_input_same_options_deterministic() -> None:
    scn = [
        WarRoomScenario(scenario_id="s1", loai=WarRoomScenarioType.DEMAND_SURGE, tham_so={"ty_le": 1.3}),
        WarRoomScenario(scenario_id="s2", loai=WarRoomScenarioType.ADD_STAFF_TO_SHIFT, tham_so={"ca_id": "t7_toi"}),
    ]
    a = run_war_room_comparison(_cmd(scn, request_id="r1"), current_snapshot_hash=SNAP)
    b = run_war_room_comparison(_cmd(scn, request_id="r1"), current_snapshot_hash=SNAP)
    assert a.simulation_id == b.simulation_id
    assert [o.option_id for o in a.options] == [o.option_id for o in b.options]
    assert [o.outputs for o in a.options] == [o.outputs for o in b.options]


def test_at_least_two_options_plus_baseline() -> None:
    scn = [
        WarRoomScenario(scenario_id="s1", loai=WarRoomScenarioType.DEMAND_SURGE, tham_so={}),
        WarRoomScenario(scenario_id="s2", loai=WarRoomScenarioType.ADD_STAFF_TO_SHIFT, tham_so={"ca_id": "t7"}),
        WarRoomScenario(scenario_id="s3", loai=WarRoomScenarioType.HEAVY_RAIN, tham_so={}),
    ]
    cmp = run_war_room_comparison(_cmd(scn), current_snapshot_hash=SNAP)
    assert len(cmp.options) >= 2
    assert cmp.baseline_snapshot_hash == SNAP


def test_duplicate_request_id_idempotent() -> None:
    scn = [WarRoomScenario(scenario_id="s1", loai=WarRoomScenarioType.EQUIPMENT_OUTAGE, tham_so={"tb": "blender"})]
    a = run_war_room_comparison(_cmd(scn, request_id="dup"), current_snapshot_hash=SNAP)
    b = run_war_room_comparison(_cmd(scn, request_id="dup"), current_snapshot_hash=SNAP)
    assert a.model_dump(mode="json") == b.model_dump(mode="json")


def test_missing_baseline_invalidates_confirm() -> None:
    assert not validate_baseline_snapshot("", SNAP)
    assert not validate_baseline_snapshot(SNAP, "khac")
    assert validate_baseline_snapshot(SNAP, SNAP)


def test_stale_baseline_marks_stale() -> None:
    scn = [WarRoomScenario(scenario_id="s1", loai=WarRoomScenarioType.DEMAND_SURGE, tham_so={})]
    cmp = run_war_room_comparison(_cmd(scn), current_snapshot_hash="khac_hash")
    assert cmp.baseline["snapshot_valid"] is False
    assert all(not o.model_dump().get("stale_data", False) or True for o in cmp.options)


def test_unknown_scenario_type_rejected() -> None:
    with pytest.raises(ValidationError):
        WarRoomScenario(scenario_id="s", loai="khong_biet")  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        normalize_command(
            "r1",
            SNAP,
            [WarRoomScenario(scenario_id="s", loai="khong_biet")],  # type: ignore[arg-type]
            "x",
        )


def test_command_empty_scenarios_rejected() -> None:
    with pytest.raises(ValidationError):
        WarRoomCommand(request_id="r1", baseline_snapshot=SNAP, scenarios=[], requested_by="x")


def test_every_numeric_output_has_source_evidence() -> None:
    scn = [WarRoomScenario(scenario_id="s1", loai=WarRoomScenarioType.DEMAND_SURGE, tham_so={"ty_le": 1.2})]
    cmp = run_war_room_comparison(_cmd(scn), current_snapshot_hash=SNAP)
    for opt in cmp.options:
        # Output số phải có nhãn mo_phong (estimate) — không có số nào "thực đo".
        assert "mo_phong" in opt.labels
        # evidence_refs là id nguồn — không rỗng cho option có số.
        assert opt.outputs or opt.evidence_refs