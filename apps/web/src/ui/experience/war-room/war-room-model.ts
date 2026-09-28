/** War Room model + presets (Phase 02). */

import type {
  WarRoomOption as WarRoomOptionContract,
  WarRoomScenario as WarRoomScenarioContract,
  WarRoomScenarioType as WarRoomScenarioTypeContract,
} from "../../../lib/contracts";

export type WarRoomScenarioType = WarRoomScenarioTypeContract;
export interface WarRoomScenarioInput
  extends Omit<WarRoomScenarioContract, "tham_so"> {
  tham_so: Record<string, string | number | boolean>;
}

/** Option thêm phần GIẢI THÍCH do backend trả (LLM khi live, tất định khi replay).
 *  Số liệu gốc vẫn từ contract; hai trường này là lớp diễn giải phụ trợ. */
export type WarRoomOption = WarRoomOptionContract & {
  reason?: string;
  reason_provider?: string;
  reason_unsupported?: string[];
};

export interface WarRoomComparison {
  simulation_id: string;
  baseline_snapshot_hash: string;
  baseline: Record<string, string | number | boolean>;
  options: WarRoomOption[];
}

export interface CrisisPreset {
  id: string;
  title: string;
  description: string;
  scenario: WarRoomScenarioInput;
}

/** Crisis Room presets — fixture rõ ràng, không giả cảm biến thật. */
export const CRISIS_PRESETS: CrisisPreset[] = [
  {
    id: "crisis_rain",
    title: "Mưa lớn",
    description: "Giảm lượt khách dự kiến 40% (mô phỏng fixture).",
    scenario: { scenario_id: "crisis_rain_scn", loai: "heavy_rain", tham_so: { ky_vong_giam_luot: 0.6 } },
  },
  {
    id: "crisis_peak",
    title: "Giờ cao điểm",
    description: "Tăng cầu 30% khung tối (mô phỏng fixture).",
    scenario: { scenario_id: "crisis_peak_scn", loai: "demand_surge", tham_so: { ty_le_gia_tang: 1.3, khung_gio: "toi" } },
  },
  {
    id: "crisis_short",
    title: "Thiếu nhân sự",
    description: "Cần thêm 1 người ca tối T7 (mô phỏng fixture).",
    scenario: {
      scenario_id: "crisis_short_scn",
      loai: "add_staff_to_shift",
      tham_so: { ca_id: "t7_toi", thu: "T7", khung: "toi", so_them: 1 },
    },
  },
  {
    id: "crisis_outage",
    title: "Thiết bị hỏng",
    description: "Mất máy xay 30 phút — giảm năng lực pha chế (mô phỏng fixture).",
    scenario: {
      scenario_id: "crisis_outage_scn",
      loai: "equipment_outage",
      tham_so: { thiet_bi: "blender-02", thoi_gian_phuc_hoi_phut: 30 },
    },
  },
  {
    id: "crisis_group",
    title: "Khách đoàn",
    description: "Đoàn 12 khách tới giờ cao điểm (mô phỏng fixture).",
    scenario: {
      scenario_id: "crisis_group_scn",
      loai: "large_group_arrival",
      tham_so: { so_khach: 12 },
    },
  },
];

export function snapshotHashForScenario(scenario: WarRoomScenarioInput): string {
  // Mỗi preset dùng hash fixture riêng (demo/replay) — deterministic.
  const map: Record<string, string> = {
    crisis_rain_scn: "snap_fixture_weather_20260918",
    crisis_peak_scn: "snap_fixture_demand_20260918",
    crisis_short_scn: "snap_fixture_staffing_20260918",
    crisis_outage_scn: "snap_fixture_equipment_20260918",
    crisis_group_scn: "snap_fixture_large_group_20260918",
  };
  return map[scenario.scenario_id] ?? "snap_fixture_demand_20260918";
}