/**
 * QUÁNVERSE — fixture MÔ PHỎNG.
 *
 * Ba kịch bản, mỗi kịch bản là một trạng thái quán HỢP LÝ và NHẤT QUÁN NỘI BỘ.
 *
 * ─── RÀNG BUỘC NHẤT QUÁN (chốt bằng test `mock.test.ts`) ────────────────────
 *
 *   1. `don_dang_xu_ly` == tổng `load` của mọi khu vực.
 *   2. `don_hom_nay` == `don_dang_xu_ly` + `don_da_xong`.
 *   3. Mọi mục khu vực trong `actions` phải trỏ tới một `zoneId` CÓ THẬT.
 *   4. KPI "Đang chờ" == tổng `queue` của mọi khu vực.
 *   5. `zones` có ĐÚNG 4 khu vực, cùng bộ zoneId với backend thật.
 *
 * Ràng buộc này CHỈ áp cho mock. Dữ liệu THẬT do máy chủ tính và có thể không
 * thoả (ví dụ đơn không gắn khu vực) — vì vậy test nhất quán chỉ chạy trên mock.
 *
 * Mọi con số ở đây là `null` khi "chưa biết", không bao giờ 0 giả.
 */

import {
  type QuanverseActionItem,
  type QuanverseCapacity,
  type QuanverseCopilot,
  type QuanverseDataQualityNotice,
  type QuanverseEvent,
  type QuanverseKpi,
  type QuanverseStoreHeader,
  type QuanverseTimelineItem,
  type QuanverseZone,
} from "../quanverse-contract";
import type { QuanverseScenario } from "./types";

export interface MockFixture {
  scenario: QuanverseScenario;
  scenarioLabel: string;
  gioVanHanh: number;
  /** Đơn đã hoàn tất trong ngày (để suy `don_hom_nay`). */
  daXong: number;
  nhanSuTrongCa: number;
  shiftLabel: string;
  zones: QuanverseZone[];
  timeline: QuanverseTimelineItem[];
  capacity: QuanverseCapacity;
  events: QuanverseEvent[];
  actions: QuanverseActionItem[];
  copilot: QuanverseCopilot;
  dataQuality: QuanverseDataQualityNotice[];
}

const KHU = {
  pha: { zoneId: "quay_pha", label: "Quầy pha chế", kind: "quay_pha" },
  thuNgan: { zoneId: "quay_thu_ngan", label: "Quầy thu ngân", kind: "quay_thu_ngan" },
  ban: { zoneId: "khu_ban", label: "Khu bàn", kind: "phong_khach" },
  kho: { zoneId: "kho", label: "Kho", kind: "kho" },
} as const;

const MUC_DAY = 5;

/** Suy trạng thái từ tải, cùng ngưỡng với backend (`services/quanverse_live.py`). */
export function trangThaiTuTai(tai: number | null): QuanverseZone["status"] {
  if (tai === null) return "chua_co_du_lieu";
  if (tai >= MUC_DAY) return "qua_tai";
  if (tai >= MUC_DAY - 1) return "chu_y";
  return "on_dinh";
}

function zone(
  base: { zoneId: string; label: string; kind: string },
  load: number | null,
  queue: number | null,
  staff: number | null,
  names: string[] = [],
): QuanverseZone {
  const status = trangThaiTuTai(load);
  const alerts: QuanverseZone["alerts"] = [];
  if (status === "qua_tai") {
    alerts.push({
      severity: "danger",
      message: `Tải ${load} vượt ngưỡng ${MUC_DAY}`,
    });
  } else if (status === "chu_y") {
    alerts.push({ severity: "warn", message: "Tải gần ngưỡng — nên theo dõi" });
  }
  return {
    zoneId: base.zoneId,
    label: base.label,
    kind: base.kind,
    status,
    load,
    threshold: MUC_DAY,
    queue,
    assignedStaff: staff,
    assignedNames: names,
    alerts,
  };
}

function capacity(points: Array<[number, number]>, daysOfData: number | null): QuanverseCapacity {
  const mapped = points.map(([hour, demand]) => ({
    hour,
    demand,
    backlog: Math.max(0, Math.round(demand - 2)),
    low: Math.max(0, Math.round((demand - 1.2) * 10) / 10),
    high: Math.round((demand + 1.2) * 10) / 10,
  }));
  const dinh = Math.max(...mapped.map((p) => p.demand));
  const tomorrow = mapped.map((p) => ({
    hour: p.hour,
    demand: Math.round(p.demand * 0.95 * 10) / 10,
    backlog: Math.max(0, Math.round(p.demand * 0.95 - 2)),
    low: Math.max(0, Math.round((p.demand * 0.95 - 1.5) * 10) / 10),
    high: Math.round((p.demand * 0.95 + 1.5) * 10) / 10,
  }));
  const dinhMai = Math.max(...tomorrow.map((p) => p.demand ?? 0));
  return {
    points: mapped,
    hasHistory: true,
    daysOfData,
    peaks: mapped.filter((p) => p.demand === dinh).map((p) => p.hour),
    weatherHint: null,
    weatherSuggestMode: null,
    weatherSuggestModeLabel: null,
    weatherNeedsLocation: false,
    confidence: (daysOfData ?? 0) >= 7 ? "cao" : (daysOfData ?? 0) >= 3 ? "trung_binh" : "thap",
    tomorrow,
    tomorrowPeaks: tomorrow.filter((p) => p.demand === dinhMai).map((p) => p.hour),
    note: `Trung bình ${daysOfData ?? "—"} ngày gần nhất · khoảng tin cậy 80%`,
  };
}

function duongNhuCau(gioCaoDiem: number): Array<[number, number]> {
  const ra: Array<[number, number]> = [];
  for (let gio = 7; gio <= 22; gio += 1) {
    const cach = Math.abs(gio - gioCaoDiem);
    ra.push([gio, cach === 0 ? 8 : Math.max(0, Math.round((8 - cach * 1.4) * 10) / 10)]);
  }
  return ra;
}

const NGUOI = ["Lan", "Minh", "Hùng", "Thảo", "Vy", "Bình"];

// ── Kịch bản 1: Ca thường ─────────────────────────────────────────────────

const BINH_THUONG: MockFixture = {
  scenario: "binh_thuong",
  scenarioLabel: "Ca thường",
  gioVanHanh: 10,
  daXong: 9,
  nhanSuTrongCa: 6,
  shiftLabel: "08:00–12:00",
  zones: [
    zone(KHU.pha, 2, 0, 2, ["Lan", "Minh"]),
    zone(KHU.thuNgan, 1, 1, 1, ["Thảo"]),
    zone(KHU.ban, 0, 0, 2, ["Hùng", "Vy"]),
    zone(KHU.kho, 0, 0, 1, ["Bình"]),
  ],
  timeline: [
    { id: "bt_tl_1", at: "10:05", title: "Bàn giao quầy pha", kind: "handover", source: "SOP", status: "sap_toi" },
    { id: "bt_tl_2", at: "10:10", title: "Kiểm tra tồn kho sữa", kind: "kiem_ke", source: "SOP", status: "sap_toi" },
  ],
  capacity: capacity(duongNhuCau(10), 4),
  events: [
    { id: "bt_ev_1", type: "process", typeLabel: "Quy trình", status: "ok", occurredAt: "10:00", source: "fixture_mock", sourceLabel: "Dữ liệu mô phỏng", summary: "Mẻ cà phê đầu ca đạt chuẩn", zoneId: "quay_pha", zoneLabel: "Quầy pha chế" },
    { id: "bt_ev_2", type: "operation_memory", typeLabel: "Ký ức vận hành", status: "ok", occurredAt: "10:06", source: "fixture_mock", sourceLabel: "Dữ liệu mô phỏng", summary: "Đã thu tiền 3 đơn chuyển khoản", zoneId: "quay_thu_ngan", zoneLabel: "Quầy thu ngân" },
  ],
  actions: [],
  copilot: {
    headline: "Quán đang ở trạng thái bình thường, chưa có điểm nghẽn.",
    reasons: [
      "Tổng tải 4 khu vực còn dưới ngưỡng.",
      "Không có cảnh báo tồn kho trong ca này.",
    ],
    citations: ["Đơn quầy", "Phân công tuần"],
    unsupportedClaims: [],
    grounded: true,
    provider: "replay",
    suggestedActions: ["Giữ nhịp hiện tại", "Kiểm tra tồn kho sữa theo lịch"],
  },
  dataQuality: [
    { code: "fixture_mock", level: "info", message: "Dữ liệu mô phỏng — kịch bản 'Ca thường'. Không phải số đo từ quán." },
  ],
};

// ── Kịch bản 2: Giờ cao điểm ──────────────────────────────────────────────

const CAO_DIEM: MockFixture = {
  scenario: "cao_diem",
  scenarioLabel: "Giờ cao điểm",
  gioVanHanh: 17,
  daXong: 34,
  nhanSuTrongCa: 6,
  shiftLabel: "14:00–18:00",
  zones: [
    zone(KHU.pha, 4, 3, 2, ["Lan", "Vy"]),
    zone(KHU.thuNgan, 2, 1, 1, ["Thảo"]),
    zone(KHU.ban, 1, 0, 2, ["Minh", "Hùng"]),
    zone(KHU.kho, 0, 0, 1, ["Bình"]),
  ],
  timeline: [
    { id: "cd_tl_1", at: "17:05", title: "Bàn giao quầy pha", kind: "handover", source: "SOP", status: "sap_toi" },
    { id: "cd_tl_2", at: "17:10", title: "Kiểm tra tồn kho sữa", kind: "kiem_ke", source: "SOP", status: "sap_toi" },
    { id: "cd_tl_3", at: "18:00", title: "Ca mới bắt đầu", kind: "doi_ca", source: "Lịch tuần", status: "sap_toi" },
    { id: "cd_tl_4", at: "18:05", title: "Kiểm tra vệ sinh khu khách", kind: "ve_sinh", source: "SOP", status: "sap_toi" },
  ],
  capacity: capacity(duongNhuCau(17), 7),
  events: [
    { id: "cd_ev_1", type: "incident", typeLabel: "Sự cố", status: "warning", occurredAt: "17:29", source: "fixture_mock", sourceLabel: "Dữ liệu mô phỏng", summary: "Quầy pha chế vượt ngưỡng tải (7 đơn)", zoneId: "quay_pha", zoneLabel: "Quầy pha chế" },
    { id: "cd_ev_2", type: "process", typeLabel: "Quy trình", status: "ok", occurredAt: "17:27", source: "fixture_mock", sourceLabel: "Dữ liệu mô phỏng", summary: "Hàng chờ thanh toán 2 đơn", zoneId: "quay_thu_ngan", zoneLabel: "Quầy thu ngân" },
    { id: "cd_ev_3", type: "signal", typeLabel: "Tín hiệu", status: "warning", occurredAt: "17:23", source: "fixture_mock", sourceLabel: "Dữ liệu mô phỏng", summary: "Ca 18:00 còn thiếu 1 người so với định biên", zoneId: null, zoneLabel: "Toàn quán" },
  ],
  actions: [
    {
      id: "cd_a_1",
      severity: "warn",
      title: "Quầy pha chế đang gần vượt ngưỡng tải",
      reason: "4 đơn đang xử lý, ngưỡng hiện tại 5; hàng chờ 3 đơn.",
      source: "Đơn quầy",
      at: null,
      ctaLabel: null,
      ctaHref: null,
    },
    {
      id: "cd_a_2",
      severity: "warn",
      title: "Ca 18:00 thiếu 1 người",
      reason: "Định biên 3 người, hiện có 2.",
      source: "Lịch tuần",
      at: null,
      ctaLabel: "Xem phân công",
      ctaHref: "/lich-tuan",
    },
  ],
  copilot: {
    headline: "Quầy pha chế đang là điểm cần theo dõi chính trong 15 phút tới.",
    reasons: [
      "Tải 4/5 đơn với hàng chờ 3 đơn — sát ngưỡng quá tải.",
      "Ca 18:00 còn thiếu 1 người so với định biên.",
      "Dự báo 17:00 là giờ cao điểm trong ngày.",
    ],
    citations: ["Đơn quầy", "Phân công tuần", "Lịch sử đơn"],
    unsupportedClaims: [],
    grounded: true,
    provider: "replay",
    suggestedActions: [
      "Chuẩn bị điều người sang quầy pha trước 18:00",
      "Kiểm tra tồn kho sữa trước giờ cao điểm",
    ],
  },
  dataQuality: [
    { code: "fixture_mock", level: "info", message: "Dữ liệu mô phỏng — kịch bản 'Giờ cao điểm'. Không phải số đo từ quán." },
  ],
};

// ── Kịch bản 3: Quầy pha quá tải ──────────────────────────────────────────

const QUA_TAI_PHA: MockFixture = {
  scenario: "qua_tai_pha",
  scenarioLabel: "Quầy pha quá tải",
  gioVanHanh: 15,
  daXong: 18,
  nhanSuTrongCa: 5,
  shiftLabel: "14:00–18:00",
  zones: [
    zone(KHU.pha, 7, 4, 2, ["Lan", "Vy"]),
    zone(KHU.thuNgan, 1, 0, 1, ["Thảo"]),
    zone(KHU.ban, 0, 0, 1, ["Minh"]),
    zone(KHU.kho, 0, 0, 1, ["Bình"]),
  ],
  timeline: [
    { id: "qt_tl_1", at: "15:05", title: "Dồn nguyên liệu sang quầy pha", kind: "tiep_ung", source: "SOP", status: "sap_toi" },
    { id: "qt_tl_2", at: "15:00", title: "Kiểm tra vệ sinh máy pha", kind: "ve_sinh", source: "SOP", status: "qua_han" },
    { id: "qt_tl_3", at: "15:15", title: "Điều 1 người từ khu bàn sang quầy pha", kind: "dieu_chuyen", source: "Phân công", status: "sap_toi" },
  ],
  capacity: capacity(duongNhuCau(15), 5),
  events: [
    { id: "qt_ev_1", type: "incident", typeLabel: "Sự cố", status: "critical", occurredAt: "15:13", source: "fixture_mock", sourceLabel: "Dữ liệu mô phỏng", summary: "Quầy pha chế quá tải kéo dài — 11 đơn dồn", zoneId: "quay_pha", zoneLabel: "Quầy pha chế" },
    { id: "qt_ev_2", type: "signal", typeLabel: "Tín hiệu", status: "warning", occurredAt: "15:01", source: "fixture_mock", sourceLabel: "Dữ liệu mô phỏng", summary: "Kho cần kiểm tra — nguyên liệu dưới ngưỡng", zoneId: "kho", zoneLabel: "Kho" },
    { id: "qt_ev_3", type: "incident", typeLabel: "Sự cố", status: "warning", occurredAt: "14:54", source: "fixture_mock", sourceLabel: "Dữ liệu mô phỏng", summary: "SOP 'vệ sinh máy pha' quá hạn", zoneId: "quay_pha", zoneLabel: "Quầy pha chế" },
  ],
  actions: [
    {
      id: "qt_a_1",
      severity: "danger",
      title: "Quầy pha chế đang vượt ngưỡng tải",
      reason: "7 đơn đang xử lý, ngưỡng hiện tại 5; hàng chờ 4 đơn.",
      source: "Đơn quầy",
      at: null,
      ctaLabel: null,
      ctaHref: null,
    },
    {
      id: "qt_a_2",
      severity: "danger",
      title: "SOP “vệ sinh máy pha” đến hạn",
      reason: "Bước vệ sinh máy pha đã qua hạn trong ca này.",
      source: "SOP",
      at: null,
      ctaLabel: "Mở SOP",
      ctaHref: "/sop",
    },
    {
      id: "qt_a_3",
      severity: "warn",
      title: "Kho cần kiểm tra",
      reason: "Nguyên liệu đã xuống dưới ngưỡng cảnh báo của quán.",
      source: "Kho",
      at: null,
      ctaLabel: "Xem tiêu thụ",
      ctaHref: "/tieu-thu",
    },
  ],
  copilot: {
    headline: "Quầy pha chế đang là điểm nghẽn chính của quán.",
    reasons: [
      "7 đơn đang xử lý với hàng chờ 4 đơn.",
      "Ngưỡng hiện tại là 5 — đã vượt 2 đơn.",
      "Chỉ có 2 nhân sự trong khu vực, trong khi khu bàn chỉ 0 đơn.",
      "SOP vệ sinh máy pha đã quá hạn.",
    ],
    citations: ["Đơn quầy", "Phân công tuần"],
    unsupportedClaims: [],
    grounded: true,
    provider: "replay",
    suggestedActions: [
      "Điều 1 người từ khu bàn sang quầy pha",
      "Hoàn tất bước vệ sinh máy pha đang quá hạn",
    ],
  },
  dataQuality: [
    { code: "fixture_mock", level: "info", message: "Dữ liệu mô phỏng — kịch bản 'Quầy pha quá tải'. Không phải số đo từ quán." },
  ],
};

export const MOCK_FIXTURES: Record<QuanverseScenario, MockFixture> = {
  binh_thuong: BINH_THUONG,
  cao_diem: CAO_DIEM,
  qua_tai_pha: QUA_TAI_PHA,
};

/** KPI suy từ fixture — CÙNG công thức với adapter thật. */
export function mockKpis(f: MockFixture): QuanverseKpi[] {
  const donDangXuLy = f.zones.reduce((s, z) => s + (z.load ?? 0), 0);
  const hangCho = f.zones.reduce((s, z) => s + (z.queue ?? 0), 0);
  return [
    { key: "staff", label: "Nhân sự đang trực", value: f.nhanSuTrongCa, tone: "neutral", source: "Phân công tuần" },
    { key: "zones", label: "Khu vực đang hoạt động", value: f.zones.length, tone: "neutral", source: "Bản chiếu vận hành" },
    { key: "orders", label: "Đơn đang xử lý", value: donDangXuLy, tone: "neutral", source: "Đơn quầy" },
    { key: "queue", label: "Đang chờ", value: hangCho, tone: "neutral", source: "Đơn quầy" },
    {
      key: "alerts",
      label: "Cảnh báo",
      value: f.actions.length,
      tone: f.actions.some((a) => a.severity === "danger") ? "danger" : f.actions.length > 0 ? "warn" : "ok",
      source: "Kho / SOP",
    },
    { key: "upcoming", label: "Việc trong 15 phút tới", value: f.timeline.length, tone: "neutral", source: "SOP / Lịch tuần" },
  ];
}

export function mockHeader(f: MockFixture): QuanverseStoreHeader {
  return {
    storeName: "Nhịp Quán",
    dateISO: new Date().toISOString().slice(0, 10),
    shiftLabel: f.shiftLabel,
    onShiftNames: NGUOI.slice(0, f.nhanSuTrongCa),
    onShiftCount: f.nhanSuTrongCa,
    systemStatus: f.actions.some((a) => a.severity === "danger")
      ? "Có điểm cần xử lý"
      : f.actions.length > 0
        ? "Theo dõi"
        : "Bình thường",
    updatedAt: new Date().toISOString(),
  };
}
