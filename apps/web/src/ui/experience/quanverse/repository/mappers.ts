/**
 * QUÁNVERSE — bộ CHUẨN HOÁ dùng chung cho cả adapter thật và adapter mô phỏng.
 *
 * Vì sao tập trung ở đây: hai adapter phải trả về CÙNG một `QuanverseViewModel`.
 * Nếu mỗi bên tự map thì hai hình dạng sẽ trôi khỏi nhau, và UI lại phải rẽ
 * nhánh theo nguồn — đúng thứ mà tầng đọc này sinh ra để tránh.
 *
 * Mọi hàm ở đây là THUẦN (không gọi mạng, không đọc state) nên test được trực
 * tiếp bằng vitest.
 */

import {
  KHONG_CO_DU_LIEU,
  type QuanverseActionItem,
  type QuanverseCapacity,
  type QuanverseCapacityPoint,
  type QuanverseCopilot,
  type QuanverseDataQualityNotice,
  type QuanverseEvent,
  type QuanverseKpi,
  type QuanverseKpiTone,
  type QuanverseStoreHeader,
  type QuanverseTimelineItem,
  type QuanverseTimelineStatus,
  type QuanverseZone,
  type QuanverseZoneStatus,
  mangHoacRong,
  soHoacNull,
} from "../quanverse-contract";

// ── Nhãn enum tiếng Việt (một chỗ duy nhất) ────────────────────────────────

const CANH_BAO_TRANG_THAI: Record<string, QuanverseZoneStatus> = {
  qua_tai: "qua_tai",
  chu_y: "chu_y",
  binh_thuong: "on_dinh",
  on_dinh: "on_dinh",
};

const CANH_BAO_TONE: Record<string, QuanverseKpiTone> = {
  qua_tai: "danger",
  chu_y: "warn",
  critical: "danger",
  error: "danger",
  warning: "warn",
  warn: "warn",
  ok: "ok",
  info: "neutral",
};

const LOAI_SU_KIEN: Record<string, string> = {
  incident: "Sự cố",
  process: "Quy trình",
  signal: "Tín hiệu",
  voice_note: "Ghi chú thoại",
  praise: "Khen ngợi",
  operation_memory: "Ký ức vận hành",
  decision: "Quyết định",
  mode_change: "Đổi chế độ",
  proposal_confirmed: "Đề xuất đã duyệt",
  proposal_rejected: "Đề xuất bị từ chối",
  anchor_status: "Trạng thái neo",
  rescue_case: "Ca cứu",
};

const NHAN_NGUON: Record<string, string> = {
  don_quay: "Đơn quầy",
  phan_cong_by_week: "Phân công tuần",
  phan_cong: "Phân công",
  lich_tuan: "Lịch tuần",
  sop: "SOP",
  fixture_mock: "Dữ liệu mô phỏng",
  fixture_replay: "Fixture replay",
  he_thong: "Hệ thống",
};

const TRANG_THAI_TIMELINE: Record<string, QuanverseTimelineStatus> = {
  sap_toi: "sap_toi",
  dang_chay: "dang_chay",
  xong: "xong",
  qua_han: "qua_han",
  da_xong: "xong",
};

export function nhanLoaiSuKien(code: unknown): string {
  if (typeof code !== "string" || !code) return "Sự kiện";
  return LOAI_SU_KIEN[code] ?? code;
}

export function nhanNguon(code: unknown): string {
  if (typeof code !== "string") return KHONG_CO_DU_LIEU;
  return NHAN_NGUON[code] ?? code;
}

export function toneTuCanhBao(code: unknown): QuanverseKpiTone {
  const key = typeof code === "string" ? code : "";
  return CANH_BAO_TONE[key] ?? "neutral";
}

export function trangThaiZoneTuCanhBao(code: unknown): QuanverseZoneStatus {
  if (code === null || code === undefined) return "chua_co_du_lieu";
  const key = typeof code === "string" ? code : "";
  return CANH_BAO_TRANG_THAI[key] ?? "chua_co_du_lieu";
}

export function trangThaiTimeline(code: unknown): QuanverseTimelineStatus {
  const key = typeof code === "string" ? code : "";
  return TRANG_THAI_TIMELINE[key] ?? "sap_toi";
}

// ── Chuẩn hoá khu vực ─────────────────────────────────────────────────────

interface ZoneTho {
  zone_id?: unknown;
  label?: unknown;
  ten?: unknown;
  kind?: unknown;
  active?: unknown;
  load_signal?: unknown;
  canh_bao?: unknown;
  tai?: unknown;
  hang_cho?: unknown;
  muc_day?: unknown;
  nhan_su?: unknown;
}

/**
 * Chuẩn hoá một khu vực từ payload `/stations` (có `tai`/`hang_cho`/`canh_bao`)
 * hoặc từ `/snapshot.zones` (chỉ có `label`/`kind`/`load_signal`).
 *
 * Cùng một hàm cho cả hai nguồn để UI chỉ đọc MỘT hình dạng khu vực.
 */
export function chuanHoaZone(
  tho: ZoneTho,
  boSung: Partial<Pick<QuanverseZone, "assignedNames">> = {},
): QuanverseZone {
  const zoneId = typeof tho.zone_id === "string" ? tho.zone_id : "";
  const label =
    typeof tho.ten === "string" && tho.ten
      ? tho.ten
      : typeof tho.label === "string" && tho.label
        ? tho.label
        : zoneId;
  const canhBao = tho.canh_bao ?? tho.load_signal;
  const load = soHoacNull(tho.tai);
  const threshold = soHoacNull(tho.muc_day);

  // Khi nguồn chỉ có `load_signal` (snapshot) mà không có số tải, trạng thái
  // vẫn suy ra được từ nhãn — nhưng `load` PHẢI giữ `null`, không được đoán 0.
  const status = trangThaiZoneTuCanhBao(canhBao);

  const alerts: QuanverseZone["alerts"] = [];
  if (status === "qua_tai") {
    alerts.push({
      severity: "danger",
      message:
        load !== null && threshold !== null
          ? `Tải ${load} vượt ngưỡng ${threshold}`
          : "Đang vượt ngưỡng tải",
    });
  } else if (status === "chu_y") {
    alerts.push({ severity: "warn", message: "Tải gần ngưỡng — nên theo dõi" });
  }

  return {
    zoneId,
    label,
    kind: typeof tho.kind === "string" ? tho.kind : "",
    status,
    load,
    threshold,
    queue: soHoacNull(tho.hang_cho),
    assignedStaff: soHoacNull(tho.nhan_su),
    assignedNames: boSung.assignedNames ?? [],
    alerts,
  };
}

// ── Timeline ──────────────────────────────────────────────────────────────

interface HorizonTho {
  item_id?: unknown;
  kind?: unknown;
  title?: unknown;
  starts_at?: unknown;
  starts_in_min?: unknown;
  source?: unknown;
  status?: unknown;
}

/** `starts_in_min` (fixture) → giờ "HH:MM" so với `gio` vận hành. */
export function gioTuPhut(gioGoc: number, phut: number): string {
  const tong = gioGoc * 60 + phut;
  const gio = Math.floor(((tong % 1440) + 1440) % 1440 / 60);
  const phutLe = ((tong % 60) + 60) % 60;
  return `${String(gio).padStart(2, "0")}:${String(phutLe).padStart(2, "0")}`;
}

export function chuanHoaTimeline(
  ds: readonly unknown[],
  gioVanHanh: number,
): QuanverseTimelineItem[] {
  return ds.map((raw, i) => {
    const h = (raw ?? {}) as HorizonTho;
    const startsAt = h.starts_at;
    let at: string;
    if (typeof startsAt === "string" && startsAt) {
      at = startsAt;
    } else {
      const phut = soHoacNull(h.starts_in_min);
      at = phut === null ? KHONG_CO_DU_LIEU : gioTuPhut(gioVanHanh, phut);
    }
    return {
      id: typeof h.item_id === "string" && h.item_id ? h.item_id : `tl_${i}`,
      at,
      title: typeof h.title === "string" ? h.title : "",
      kind: typeof h.kind === "string" ? h.kind : "",
      source: nhanNguon(h.source),
      status: trangThaiTimeline(h.status),
    };
  });
}

// ── Năng lực / dự báo ─────────────────────────────────────────────────────

interface SeriesTho {
  gio?: unknown;
  nhu_cau?: unknown;
  hang_doi_du_bao?: unknown;
}

/**
 * Chuẩn hoá chuỗi dự báo. Khi `co_du_lieu = false`, nhu cầu PHẢI là `null` cho
 * mọi điểm — UI sẽ nói "chưa đủ dữ liệu lịch sử" thay vì vẽ một đường phẳng 0
 * trông như dữ liệu thật.
 */
export function chuanHoaCapacity(
  series: readonly unknown[],
  coDuLieu: boolean,
  soNgay: unknown,
  dinh: readonly unknown[],
): QuanverseCapacity {
  const points: QuanverseCapacityPoint[] = series.map((raw) => {
    const s = (raw ?? {}) as SeriesTho;
    return {
      hour: soHoacNull(s.gio) ?? 0,
      demand: coDuLieu ? soHoacNull(s.nhu_cau) : null,
      backlog: coDuLieu ? soHoacNull(s.hang_doi_du_bao) : null,
    };
  });
  const peaks = coDuLieu
    ? mangHoacRong(dinh)
        .map((g) => soHoacNull(g))
        .filter((g): g is number => g !== null)
    : [];
  return {
    points,
    hasHistory: coDuLieu && points.some((p) => p.demand !== null),
    daysOfData: soHoacNull(soNgay),
    peaks,
    weatherHint: null,
  };
}

// ── AI copilot ────────────────────────────────────────────────────────────

interface BriefTho {
  headline?: unknown;
  facts?: unknown;
  risks?: unknown;
  next_actions?: unknown;
  grounded_refs?: unknown;
}

interface AskTho {
  answer?: unknown;
  citations?: unknown;
  unsupported_claims?: unknown;
  grounded?: unknown;
  provider?: unknown;
  brief?: BriefTho;
}

function chuoiTuMang(value: unknown): string[] {
  return mangHoacRong(value as readonly unknown[])
    .map((v) => (typeof v === "string" ? v.trim() : ""))
    .filter((v) => v.length > 0);
}

/**
 * Ghép `QuanverseBrief` + `QuanverseAskResponse` thành một khối copilot.
 *
 * Lưu ý: backend KHÔNG trả trường độ tin cậy dạng số — chỉ có `grounded`
 * (boolean). Hợp đồng ở đây phản ánh đúng thực tế đó, không bịa thêm.
 */
export function chuanHoaCopilot(
  brief: BriefTho | null,
  ask: AskTho | null,
  fallbackHeadline: string,
): QuanverseCopilot | null {
  if (!brief && !ask) return null;
  const headline =
    typeof ask?.answer === "string" && ask.answer.trim()
      ? ask.answer.trim()
      : typeof brief?.headline === "string"
        ? brief.headline
        : fallbackHeadline;
  const reasons = [
    ...chuoiTuMang(brief?.facts),
    ...chuoiTuMang(brief?.risks),
  ];
  const citations = chuoiTuMang(ask?.citations ?? brief?.grounded_refs);
  return {
    headline,
    reasons,
    citations,
    unsupportedClaims: chuoiTuMang(ask?.unsupported_claims),
    grounded: ask?.grounded === true || citations.length > 0,
    provider: typeof ask?.provider === "string" ? ask.provider : "replay",
    suggestedActions: chuoiTuMang(brief?.next_actions),
  };
}

// ── Sự kiện ───────────────────────────────────────────────────────────────

interface EventTho {
  event_id?: unknown;
  event_type?: unknown;
  status?: unknown;
  occurred_at?: unknown;
  minutes_ago?: unknown;
  source?: unknown;
  summary?: unknown;
  zone_id?: unknown;
}

export function chuanHoaEvents(
  ds: readonly unknown[],
  zoneLabelById: ReadonlyMap<string, string>,
): QuanverseEvent[] {
  return ds.map((raw, i) => {
    const e = (raw ?? {}) as EventTho;
    const zoneId = typeof e.zone_id === "string" && e.zone_id ? e.zone_id : null;
    const occurred = e.occurred_at;
    let occurredAt: string;
    if (typeof occurred === "string" && occurred) {
      occurredAt = occurred;
    } else {
      const phut = soHoacNull(e.minutes_ago);
      occurredAt = phut === null ? KHONG_CO_DU_LIEU : `${Math.round(phut)} phút trước`;
    }
    return {
      id: typeof e.event_id === "string" && e.event_id ? e.event_id : `ev_${i}`,
      type: typeof e.event_type === "string" ? e.event_type : "",
      typeLabel: nhanLoaiSuKien(e.event_type),
      status: typeof e.status === "string" ? e.status : "",
      occurredAt,
      source: typeof e.source === "string" ? e.source : "",
      sourceLabel: nhanNguon(e.source),
      summary: typeof e.summary === "string" ? e.summary : "",
      zoneId,
      zoneLabel: zoneId ? (zoneLabelById.get(zoneId) ?? zoneId) : "Toàn quán",
    };
  });
}

// ── Chất lượng dữ liệu ────────────────────────────────────────────────────

export function chuanHoaDataQuality(value: unknown): QuanverseDataQualityNotice[] {
  return mangHoacRong(value as readonly unknown[])
    .map((q) => {
      const o = (q ?? {}) as {
        code?: unknown;
        level?: unknown;
        message?: unknown;
      };
      const level =
        o.level === "warning" || o.level === "error" ? o.level : "info";
      return {
        code: typeof o.code === "string" ? o.code : "unknown",
        level,
        message: typeof o.message === "string" ? o.message : "",
      } as QuanverseDataQualityNotice;
    })
    .filter((q) => q.message.length > 0 || q.code !== "unknown");
}

// ── KPI ───────────────────────────────────────────────────────────────────

export function kpi(
  key: QuanverseKpi["key"],
  label: string,
  value: number | null,
  tone: QuanverseKpiTone,
  source: string,
  unit?: string,
): QuanverseKpi {
  return { key, label, value, tone, source, unit };
}

// ── Action items ──────────────────────────────────────────────────────────

export function chuanHoaActions(
  items: readonly QuanverseActionItem[],
): QuanverseActionItem[] {
  return [...items].sort((a, b) => {
    const rank: Record<QuanverseKpiTone, number> = {
      danger: 0,
      warn: 1,
      neutral: 2,
      ok: 3,
    };
    return rank[a.severity] - rank[b.severity];
  });
}

// ── Header ────────────────────────────────────────────────────────────────

export function chuanHoaHeader(
  tho: Partial<QuanverseStoreHeader> & { storeName?: string },
): QuanverseStoreHeader {
  return {
    storeName: tho.storeName ?? "Nhịp Quán",
    dateISO: tho.dateISO ?? new Date().toISOString().slice(0, 10),
    shiftLabel: tho.shiftLabel ?? null,
    onShiftNames: mangHoacRong(tho.onShiftNames),
    onShiftCount: soHoacNull(tho.onShiftCount),
    systemStatus: tho.systemStatus ?? "Bình thường",
    updatedAt: tho.updatedAt ?? null,
  };
}
