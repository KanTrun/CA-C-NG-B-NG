"""War Room determinism tests — cùng input → cùng output byte-equivalent."""

from __future__ import annotations

import json
from typing import Any

from ca_agents.ag_war_room import run_war_room_comparison
from ca_agents.ag_war_room.command import WarRoomCommand
from ca_contracts import WarRoomScenario, WarRoomScenarioType

SNAP = "snap_20260918_1234abcd"


def _run(times: int = 1) -> list[dict[str, Any]]:
    scn = [
        WarRoomScenario(scenario_id="s1", loai=WarRoomScenarioType.DEMAND_SURGE, tham_so={"ty_le": 1.3}),
        WarRoomScenario(scenario_id="s2", loai=WarRoomScenarioType.ADD_STAFF_TO_SHIFT, tham_so={"ca_id": "t7_toi", "thu": "T7", "khung": "toi"}),
    ]
    cmd = WarRoomCommand(
        request_id="det_req_1",
        baseline_snapshot=SNAP,
        scenarios=scn,
        requested_by="quan_ly_test",
    )
    results = []
    for _ in range(times):
        cmp = run_war_room_comparison(cmd, current_snapshot_hash=SNAP)
        results.append(cmp.model_dump(mode="json"))
    return results


def test_war_room_deterministic_byte_equal() -> None:
    results = _run(3)
    first = json.dumps(results[0], sort_keys=True)
    for r in results[1:]:
        assert json.dumps(r, sort_keys=True) == first


def test_deterministic_stable_ordering() -> None:
    """Thứ tự option phải giữ nguyên khi input giữ nguyên."""
    results = _run(2)
    assert [o["option_id"] for o in results[0]["options"]] == [
        o["option_id"] for o in results[1]["options"]
    ]