/**
 * QUÁNVERSE — adapter MÔ PHỎNG.
 *
 * Trả CÙNG `QuanverseViewModel` như adapter thật, chỉ khác `dataSource: "mock"`
 * và có `scenario`. UI không rẽ nhánh theo nguồn — nó chỉ đọc hợp đồng.
 *
 * Dữ liệu đến từ `mock-data.ts` (fixture biên soạn tay, nhất quán nội bộ).
 * KHÔNG đọc mạng, KHÔNG ghi gì.
 */

import {
  type QuanverseProvenance,
  type QuanverseViewModel,
} from "../quanverse-contract";
import { MOCK_FIXTURES, mockHeader, mockKpis } from "./mock-data";
import type { QuanverseReadOptions, QuanverseRepository, QuanverseScenario } from "./types";

const MAC_DINH: QuanverseScenario = "cao_diem";

export class MockQuanverseRepository implements QuanverseRepository {
  readonly dataSource = "mock" as const;

  constructor(private readonly scenarioDefault: QuanverseScenario = MAC_DINH) {}

  async getViewModel(opts: QuanverseReadOptions): Promise<QuanverseViewModel> {
    const scenario = opts.scenario ?? this.scenarioDefault;
    const f = MOCK_FIXTURES[scenario] ?? MOCK_FIXTURES[MAC_DINH];

    // Nguồn được khai TRUNG THỰC: đây là fixture, không phải API.
    const provenance: QuanverseProvenance[] = [
      {
        label: "Bộ dữ liệu mô phỏng",
        endpoint: `fixture://quanverse/${f.scenario}`,
        ok: true,
      },
    ];

    return {
      dataSource: "mock",
      scenario: f.scenario,
      scenarioLabel: f.scenarioLabel,
      role: opts.role,
      header: mockHeader(f),
      kpis: mockKpis(f),
      zones: f.zones,
      actions: f.actions,
      timeline: f.timeline,
      capacity: f.capacity,
      copilot: f.copilot,
      events: f.events,
      dataQuality: f.dataQuality,
      provenance,
    };
  }
}
