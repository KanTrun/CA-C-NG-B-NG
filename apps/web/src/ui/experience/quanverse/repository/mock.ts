/**
 * QUÁNVERSE — adapter MÔ PHỎNG.
 *
 * Trả CÙNG `QuanverseViewModel` như adapter thật, chỉ khác `dataSource: "mock"`
 * và có `scenario`. UI không rẽ nhánh theo nguồn — nó chỉ đọc hợp đồng.
 *
 * Dữ liệu đến từ `mock-data.ts` (fixture biên soạn tay, nhất quán nội bộ).
 * KHÔNG đọc mạng, KHÔNG ghi gì lên máy chủ — modes giữ state trong bộ nhớ
 * phiên để demo propose → confirm.
 */

import type {
  QuanverseAskResult,
  QuanverseMode,
  QuanverseModesState,
  QuanverseViewModel,
} from "../quanverse-contract";
import { chuanHoaAsk } from "./mappers";
import { MOCK_FIXTURES, mockHeader, mockKpis } from "./mock-data";
import type {
  QuanverseAskOptions,
  QuanverseReadOptions,
  QuanverseRepository,
  QuanverseScenario,
} from "./types";
import { QUANVERSE_MODE_LABEL } from "./types";

const MAC_DINH: QuanverseScenario = "cao_diem";

const MOCK_MODE_CODES = [
  "gio_cao_diem",
  "troi_mua",
  "khach_doan",
  "thieu_nhan_su",
  "quan_yen_tinh",
  "dem_nhac",
] as const;

const MOCK_MODE_EFFECT: Record<string, string> = {
  gio_cao_diem: "Bật gợi ý san ca và cảnh báo quầy quá tải.",
  troi_mua: "Dồn chỗ ngồi trong nhà, ưu tiên món nóng.",
  khach_doan: "Gom bàn, chuẩn bị đón đoàn và xếp trước.",
  thieu_nhan_su: "Mở luồng cứu ca và xếp hạng người bù.",
  quan_yen_tinh: "Giảm nhạc, hạn chế thông báo không khẩn.",
  dem_nhac: "Bật lịch nhạc, giữ khu vực sân khấu.",
};

const MOCK_MODE_AFFECTS: Record<string, string[]> = {
  troi_mua: ["khu_ngoai_troi", "khach_vao", "den_bao_mua"],
  gio_cao_diem: ["quay_pha_che", "thu_ngan", "nhan_su"],
  khach_doan: ["ban_lon", "kho", "dich_vu"],
  thieu_nhan_su: ["nhan_su", "nang_luc", "crisis"],
  quan_yen_tinh: ["khong_gian", "den", "nhac"],
  dem_nhac: ["am_nhac", "khong_gian", "bar"],
};

/** State modes trong phiên — tách theo instance scenario để demo không lẫn. */
const mockModeState = new Map<string, { active: boolean; proposalStatus: string }>();

function modeKey(scenario: QuanverseScenario, mode: string): string {
  return `${scenario}:${mode}`;
}

function buildModes(
  scenario: QuanverseScenario,
  role: QuanverseModesState["role"],
): QuanverseModesState {
  const canActivate = role === "quan_ly" || role === "chu_quan";
  const modes: QuanverseMode[] = MOCK_MODE_CODES.map((code) => {
    const st = mockModeState.get(modeKey(scenario, code)) ?? {
      active: scenario === "cao_diem" && code === "gio_cao_diem",
      proposalStatus:
        scenario === "cao_diem" && code === "gio_cao_diem" ? "confirmed" : "",
    };
    const status = st.active ? "active" : st.proposalStatus === "draft" ? "draft" : "off";
    return {
      mode: code,
      label: QUANVERSE_MODE_LABEL[code] ?? code,
      active: st.active,
      proposalStatus: st.proposalStatus,
      status,
      effect: MOCK_MODE_EFFECT[code] ?? "",
      affectedProjections: MOCK_MODE_AFFECTS[code] ?? [],
    };
  });
  return { modes, canActivate, role };
}

export class MockQuanverseRepository implements QuanverseRepository {
  readonly dataSource = "mock" as const;

  constructor(private readonly scenarioDefault: QuanverseScenario = MAC_DINH) {}

  private scenarioHienTai(opts?: QuanverseReadOptions): QuanverseScenario {
    return opts?.scenario ?? this.scenarioDefault;
  }

  async askQuestion(opts: QuanverseAskOptions): Promise<QuanverseAskResult> {
    const question = opts.question.trim();
    const f = MOCK_FIXTURES[this.scenarioDefault] ?? MOCK_FIXTURES[MAC_DINH];
    const copilot = f.copilot;
    // Trả lời deterministic từ brief fixture — không gọi LLM.
    const answer = [
      copilot.headline,
      ...copilot.reasons.slice(0, 2),
      question ? `Liên quan câu hỏi: “${question}”.` : "",
    ]
      .filter(Boolean)
      .join(" ");
    return chuanHoaAsk(
      {
        answer,
        citations: copilot.citations,
        unsupported_claims: copilot.unsupportedClaims,
        grounded: copilot.grounded,
        provider: "replay",
      },
      question,
    );
  }

  async listModes(): Promise<QuanverseModesState> {
    return buildModes(this.scenarioDefault, "quan_ly");
  }

  async proposeMode(mode: string): Promise<QuanverseModesState> {
    const key = modeKey(this.scenarioDefault, mode);
    const cur = mockModeState.get(key) ?? { active: false, proposalStatus: "" };
    if (!cur.active) {
      mockModeState.set(key, { active: false, proposalStatus: "draft" });
    }
    return this.listModes();
  }

  async confirmMode(mode: string): Promise<QuanverseModesState> {
    mockModeState.set(modeKey(this.scenarioDefault, mode), {
      active: true,
      proposalStatus: "confirmed",
    });
    return this.listModes();
  }

  async deactivateMode(mode: string): Promise<QuanverseModesState> {
    mockModeState.set(modeKey(this.scenarioDefault, mode), {
      active: false,
      proposalStatus: "",
    });
    return this.listModes();
  }

  async getViewModel(opts: QuanverseReadOptions): Promise<QuanverseViewModel> {
    const scenario = this.scenarioHienTai(opts);
    const f = MOCK_FIXTURES[scenario] ?? MOCK_FIXTURES[MAC_DINH];

    const provenance = [
      {
        label: "Bộ dữ liệu mô phỏng",
        endpoint: `fixture://quanverse/${f.scenario}`,
        ok: true as const,
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
