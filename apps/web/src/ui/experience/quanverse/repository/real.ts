/**
 * QUÁNVERSE — adapter ĐỌC DỮ LIỆU THẬT.
 *
 * Ghép sáu nguồn đang có sẵn thành MỘT `QuanverseViewModel`. Không dựng API
 * trùng lặp, không ghi gì, không gọi LLM cho phần số.
 *
 * ─── NGUYÊN TẮC CHỊU LỖI ──────────────────────────────────────────────────
 *
 * Mỗi nguồn nằm trong `try/catch` RIÊNG. Một nguồn hỏng ⇒ các trường của nó
 * thành `null`/`[]` và được ghi vào `provenance` với `ok:false`; trang KHÔNG
 * sập và KHÔNG hiện số 0 giả.
 *
 * ─── NGUỒN ────────────────────────────────────────────────────────────────
 *
 *   /api/v1/experience/quanverse/snapshot      zones · events · next_horizon · role
 *   /api/v1/experience/quanverse/stations      tải · hàng chờ · chỉ số (ĐƠN THẬT)
 *   /api/v1/experience/quanverse/forecast      dự báo theo giờ (LỊCH SỬ ĐƠN THẬT)
 *   /api/v1/experience/quanverse/brief/living_map   tóm tắt tất định cho AI copilot
 *   /api/v1/lich-tuan                          phân công tuần → suy TÊN người trực
 *   /api/v1/hom-nay                            cảnh báo tồn · việc treo · việc tới hạn
 *
 * LƯU Ý VỀ KHOẢNG TRỐNG (ghi rõ để không ai tưởng là bug):
 * Backend CHƯA có endpoint "ai đang trực ngay bây giờ". `stations.chi_so.nhan_su_trong_ca`
 * chỉ là một CON SỐ. Tên người trực được suy ra ở đây từ `lich-tuan` (phân công
 * tuần + danh mục ca, lọc theo giờ hiện tại). Khi không khớp được ca nào, tên để
 * RỖNG và UI hiện "—" — không đoán.
 */

import { ApiError, apiGet, apiSend } from "../../../../lib/api";
import { getRole } from "../../../../lib/session";
import {
  type QuanverseActionItem,
  type QuanverseAskResult,
  type QuanverseKpi,
  type QuanverseModesState,
  type QuanverseProvenance,
  type QuanverseRole,
  type QuanverseViewModel,
  type QuanverseZone,
  mangHoacRong,
  mangTho,
  soHoacNull,
} from "../quanverse-contract";
import {
  chuanHoaActions,
  chuanHoaAsk,
  chuanHoaCapacity,
  chuanHoaCopilot,
  chuanHoaDataQuality,
  chuanHoaEvents,
  chuanHoaHeader,
  chuanHoaModes,
  chuanHoaTimeline,
  chuanHoaZone,
  kpi,
} from "./mappers";
import type {
  QuanverseAskOptions,
  QuanverseReadOptions,
  QuanverseRepository,
} from "./types";

// ── Hình dạng thô của các nguồn (chỉ khai trường mình đọc) ─────────────────

interface StationsTho {
  co_du_lieu?: unknown;
  gio?: unknown;
  tuan_iso?: unknown;
  stations?: unknown;
  chi_so?: Record<string, unknown>;
}

interface ForecastTho {
  co_du_lieu?: unknown;
  so_ngay_du_lieu?: unknown;
  series?: unknown;
  giao_dich_nhat?: unknown;
}

interface ThoiTietTho {
  co_du_lieu?: unknown;
  anh_huong_quan?: {
    tom_tat?: unknown;
    de_xuat_mode?: unknown;
    de_xuat_mode_label?: unknown;
  };
  hien_tai?: {
    mo_ta?: unknown;
    nhiet_do?: unknown;
  };
}

interface SnapshotTho {
  snapshot_id?: unknown;
  store_id?: unknown;
  generated_at?: unknown;
  role?: unknown;
  zones?: unknown;
  events?: unknown;
  next_horizon?: unknown;
  data_quality?: unknown;
}

interface BriefTho {
  headline?: unknown;
  facts?: unknown;
  risks?: unknown;
  next_actions?: unknown;
  grounded_refs?: unknown;
  metrics?: unknown;
}

interface NhanVienTho {
  id?: unknown;
  ten?: unknown;
  name?: unknown;
}

interface CaTho {
  id?: unknown;
  thu?: unknown;
  khung?: unknown;
  bat_dau?: unknown;
  ket_thuc?: unknown;
  vi_tri?: unknown;
  so_nguoi_toi_thieu?: unknown;
}

interface LichTuanTho {
  tuan_iso?: unknown;
  nhan_vien?: unknown;
  ca?: unknown;
  phan_cong?: unknown;
  nguon_lich?: unknown;
}

interface ViecTho {
  id?: unknown;
  tieu_de?: unknown;
  chi_tiet?: unknown;
  noi_dung?: unknown;
  trang_thai?: unknown;
  link?: unknown;
  muc?: unknown;
}

interface HomNayTho {
  ngay?: unknown;
  canh_bao_ton?: unknown;
  so_treo?: unknown;
  treo_preview?: unknown;
  viec_cho_toi?: unknown;
}

// ── Tiện ích ───────────────────────────────────────────────────────────────

/** Giờ hiện tại theo UTC+7 (giờ quán), khớp cách backend tính `gio`. */
function gioQuanHienTai(now = new Date()): { gio: number; phut: number; thu: number } {
  const vn = new Date(now.getTime() + (7 * 60 + now.getTimezoneOffset()) * 60_000);
  return { gio: vn.getHours(), phut: vn.getMinutes(), thu: vn.getDay() };
}

function phutTuHHMM(value: unknown): number | null {
  if (typeof value !== "string") return null;
  const m = value.match(/^(\d{1,2}):(\d{2})/);
  if (!m) return null;
  return Number(m[1]) * 60 + Number(m[2]);
}

function nhanNhanVien(nv: NhanVienTho): string {
  if (typeof nv.ten === "string" && nv.ten) return nv.ten;
  if (typeof nv.name === "string" && nv.name) return nv.name;
  return "";
}

/** Kết quả một lần đọc: dữ liệu + trạng thái để ghi vào `provenance`. */
interface KetQua<T> {
  data: T | null;
  ok: boolean;
  status?: number;
  missing: string[];
}

async function doc<T>(
  label: string,
  endpoint: string,
  path: string,
  missing: string[],
): Promise<KetQua<T>> {
  try {
    const data = await apiGet<T>(path);
    return { data, ok: true, missing: [] };
  } catch (e) {
    const status = e instanceof ApiError ? e.status : undefined;
    void label;
    void endpoint;
    return { data: null, ok: false, status, missing };
  }
}

// ── Suy TÊN nhân sự đang trực từ lịch tuần ─────────────────────────────────

interface NguoiTruc {
  names: string[];
  count: number | null;
  shiftLabel: string | null;
}

/**
 * Suy nhân sự đang trực: lọc ca của HÔM NAY theo giờ hiện tại, rồi tra
 * `phan_cong` (ca_id → nv_id) sang tên.
 *
 * Trả `count: null` khi KHÔNG đọc được lịch tuần — khác với "có lịch nhưng
 * không ai trực" (`count: 0`). UI phân biệt hai trường hợp này.
 */
export function suyNguoiTruc(
  lich: LichTuanTho | null,
  gioHienTai: number,
  phutHienTai: number,
  thuHienTai: number,
): NguoiTruc {
  if (!lich) return { names: [], count: null, shiftLabel: null };

  const caRaw = mangHoacRong(lich.ca as readonly CaTho[]);
  const phanCong = (lich.phan_cong ?? {}) as Record<string, unknown>;
  const tenTheoId = new Map<string, string>();
  for (const nv of mangHoacRong(lich.nhan_vien as readonly NhanVienTho[])) {
    const id = typeof nv.id === "string" ? nv.id : "";
    if (id) tenTheoId.set(id, nhanNhanVien(nv));
  }

  const phutBayGio = gioHienTai * 60 + phutHienTai;
  const tenDangTruc = new Set<string>();
  let nguoiTrongCa = 0;
  let nhanCa: string | null = null;

  for (const ca of caRaw) {
    const caId = typeof ca.id === "string" ? ca.id : "";
    if (!caId) continue;
    const batDau = phutTuHHMM(ca.bat_dau);
    const ketThuc = phutTuHHMM(ca.ket_thuc);
    if (batDau === null || ketThuc === null) continue;

    // Ca của hôm nay: `thu` là chỉ số 0..6 khớp `getDay()`; thiếu `thu` thì
    // coi như mọi ngày (lịch tuần dựng từ seed không luôn ghi `thu`).
    const thuCa = soHoacNull(ca.thu);
    if (thuCa !== null && thuCa !== thuHienTai) continue;

    // Ca qua đêm (ket_thuc < bat_dau) phải so vòng.
    const trongCa =
      ketThuc >= batDau
        ? phutBayGio >= batDau && phutBayGio < ketThuc
        : phutBayGio >= batDau || phutBayGio < ketThuc;
    if (!trongCa) continue;

    const nguoi = mangHoacRong(phanCong[caId] as readonly unknown[]);
    nguoiTrongCa += nguoi.length;
    for (const nvId of nguoi) {
      const ten = tenTheoId.get(String(nvId));
      if (ten) tenDangTruc.add(ten);
    }
    nhanCa = `${String(ca.bat_dau ?? "")}–${String(ca.ket_thuc ?? "")}`;
  }

  // Chỉ trả `count` khi THẬT SỰ tìm được ca nào đó phủ giờ hiện tại. Không có
  // ca nào phủ ⇒ `null` (chưa suy ra được), không phải 0 (vắng người).
  const coCa = nhanCa !== null;
  return {
    names: [...tenDangTruc].sort((a, b) => a.localeCompare(b, "vi")),
    count: coCa ? nguoiTrongCa : null,
    shiftLabel: nhanCa,
  };
}

// ── Adapter ────────────────────────────────────────────────────────────────

interface StaffOnShiftTho {
  names?: unknown;
  count?: unknown;
  shift_label?: unknown;
  co_du_lieu?: unknown;
}

export class RealQuanverseRepository implements QuanverseRepository {
  readonly dataSource = "real" as const;

  async askQuestion(opts: QuanverseAskOptions): Promise<QuanverseAskResult> {
    const question = opts.question.trim();
    try {
      const raw = await apiSend<{
        question?: unknown;
        answer?: unknown;
        citations?: unknown;
        unsupported_claims?: unknown;
        grounded?: unknown;
        provider?: unknown;
      }>("/api/v1/experience/quanverse/ask", {
        page: opts.page ?? "living_map",
        question,
      });
      return chuanHoaAsk(raw, question);
    } catch {
      return chuanHoaAsk(null, question);
    }
  }

  async listModes(): Promise<QuanverseModesState> {
    try {
      const raw = await apiGet<{
        modes?: unknown;
        can_activate?: unknown;
        role?: unknown;
      }>("/api/v1/experience/quanverse/modes");
      return chuanHoaModes(raw);
    } catch {
      return chuanHoaModes(null);
    }
  }

  async proposeMode(mode: string): Promise<QuanverseModesState> {
    await apiSend(`/api/v1/experience/quanverse/modes/${encodeURIComponent(mode)}/propose`);
    return this.listModes();
  }

  async confirmMode(mode: string): Promise<QuanverseModesState> {
    await apiSend(`/api/v1/experience/quanverse/modes/${encodeURIComponent(mode)}/confirm`);
    return this.listModes();
  }

  async deactivateMode(mode: string): Promise<QuanverseModesState> {
    await apiSend(`/api/v1/experience/quanverse/modes/${encodeURIComponent(mode)}/deactivate`);
    return this.listModes();
  }

  async getViewModel(opts: QuanverseReadOptions): Promise<QuanverseViewModel> {
    const role = (opts.role ?? getRole() ?? "quan_ly") as QuanverseRole;
    const provenance: QuanverseProvenance[] = [];

    const [snap, stations, forecast, brief, lich, homNay, thoiTiet, staff] = await Promise.all([
      doc<SnapshotTho>(
        "Bản chiếu vận hành",
        "/api/v1/experience/quanverse/snapshot",
        `/api/v1/experience/quanverse/snapshot?replay_role=${encodeURIComponent(role)}`,
        ["zones", "events", "next_horizon"],
      ),
      doc<StationsTho>(
        "Tải theo khu vực",
        "/api/v1/experience/quanverse/stations",
        "/api/v1/experience/quanverse/stations",
        ["stations", "chi_so"],
      ),
      doc<ForecastTho>(
        "Dự báo nhu cầu",
        "/api/v1/experience/quanverse/forecast",
        "/api/v1/experience/quanverse/forecast",
        ["series"],
      ),
      doc<BriefTho>(
        "Tóm tắt cho AI",
        "/api/v1/experience/quanverse/brief/living_map",
        "/api/v1/experience/quanverse/brief/living_map",
        ["headline", "facts"],
      ),
      doc<LichTuanTho>(
        "Phân công tuần",
        "/api/v1/lich-tuan",
        "/api/v1/lich-tuan",
        ["phan_cong", "ca"],
      ),
      doc<HomNayTho>(
        "Việc và cảnh báo",
        "/api/v1/hom-nay",
        "/api/v1/hom-nay",
        ["viec_cho_toi", "canh_bao_ton"],
      ),
      doc<ThoiTietTho>(
        "AI Forecast thời tiết",
        "/api/v1/thoi-tiet/hom-nay",
        "/api/v1/thoi-tiet/hom-nay",
        ["co_du_lieu"],
      ),
      doc<StaffOnShiftTho>(
        "Nhân sự trong ca",
        "/api/v1/experience/quanverse/staff-on-shift",
        "/api/v1/experience/quanverse/staff-on-shift",
        ["names", "count"],
      ),
    ]);

    provenance.push(
      { label: "Bản chiếu vận hành", endpoint: "/api/v1/experience/quanverse/snapshot", ok: snap.ok, status: snap.status, missingFields: snap.missing },
      { label: "Tải theo khu vực", endpoint: "/api/v1/experience/quanverse/stations", ok: stations.ok, status: stations.status, missingFields: stations.missing },
      { label: "Dự báo nhu cầu", endpoint: "/api/v1/experience/quanverse/forecast", ok: forecast.ok, status: forecast.status, missingFields: forecast.missing },
      { label: "Tóm tắt cho AI", endpoint: "/api/v1/experience/quanverse/brief/living_map", ok: brief.ok, status: brief.status, missingFields: brief.missing },
      { label: "Phân công tuần", endpoint: "/api/v1/lich-tuan", ok: lich.ok, status: lich.status, missingFields: lich.missing },
      { label: "Việc và cảnh báo", endpoint: "/api/v1/hom-nay", ok: homNay.ok, status: homNay.status, missingFields: homNay.missing },
      { label: "AI Forecast thời tiết", endpoint: "/api/v1/thoi-tiet/hom-nay", ok: thoiTiet.ok, status: thoiTiet.status, missingFields: thoiTiet.missing },
      { label: "Nhân sự trong ca", endpoint: "/api/v1/experience/quanverse/staff-on-shift", ok: staff.ok, status: staff.status, missingFields: staff.missing },
    );

    // ── Khu vực: ưu tiên `/stations` (có số tải), bù bằng `/snapshot.zones` ──
    const stationsBody = stations.data;
    const snapBody = snap.data;

    const zones: QuanverseZone[] = [];
    const zoneLabelById = new Map<string, string>();
    if (stationsBody?.stations) {
      for (const z of mangHoacRong(stationsBody.stations as readonly unknown[])) {
        const zone = chuanHoaZone(z as Record<string, unknown>);
        // Chưa có đơn quầy thật → không trình bày tải 0 như "quán rảnh đo được".
        if (stationsBody.co_du_lieu !== true) {
          zone.load = null;
          zone.queue = null;
          zone.status = "chua_co_du_lieu";
          zone.alerts = [];
        }
        zones.push(zone);
        zoneLabelById.set(zone.zoneId, zone.label);
      }
    }
    if (zones.length === 0 && snapBody?.zones) {
      for (const z of mangHoacRong(snapBody.zones as readonly unknown[])) {
        const zone = chuanHoaZone(z as Record<string, unknown>);
        zones.push(zone);
        zoneLabelById.set(zone.zoneId, zone.label);
      }
    }

    // ── Nhân sự đang trực: ưu tiên endpoint chuyên dụng, fallback lịch tuần ──
    const { gio, phut, thu } = gioQuanHienTai();
    const suyTuLich = suyNguoiTruc(lich.data, gio, phut, thu);
    const staffBody = staff.data;
    const nguoiTruc = staff.ok && staffBody
      ? {
          names: mangHoacRong(staffBody.names as readonly string[]).filter(
            (n): n is string => typeof n === "string" && n.length > 0,
          ),
          count: soHoacNull(staffBody.count) ?? suyTuLich.count,
          shiftLabel:
            typeof staffBody.shift_label === "string" && staffBody.shift_label
              ? staffBody.shift_label
              : suyTuLich.shiftLabel,
        }
      : suyTuLich;

    // ── KPI ────────────────────────────────────────────────────────────────
    const chiSo = (stationsBody?.chi_so ?? {}) as Record<string, unknown>;
    const coDonThat = stationsBody?.co_du_lieu === true;
    const soCanhBao = mangHoacRong(homNay.data?.canh_bao_ton as readonly unknown[]).length;
    const soViecToi = mangHoacRong(homNay.data?.viec_cho_toi as readonly unknown[]).length;
    const soZoneHoatDong = zones.filter((z) => z.status !== "chua_co_du_lieu").length;

    const kpis: QuanverseKpi[] = [
      // Nhân sự: lấy SỐ suy từ lịch trước, bù bằng chỉ số của `/stations`.
      kpi(
        "staff",
        "Nhân sự đang trực",
        nguoiTruc.count ?? (coDonThat ? soHoacNull(chiSo.nhan_su_trong_ca) : null),
        "neutral",
        "Phân công tuần",
      ),
      kpi(
        "zones",
        "Khu vực đang hoạt động",
        zones.length > 0 ? soZoneHoatDong : null,
        "neutral",
        "Bản chiếu vận hành",
      ),
      kpi(
        "orders",
        "Đơn đang xử lý",
        coDonThat ? soHoacNull(chiSo.don_dang_xu_ly) : null,
        "neutral",
        "Đơn quầy",
      ),
      kpi(
        "queue",
        "Đang chờ",
        zones.length > 0 && zones.some((z) => z.queue !== null)
          ? zones.reduce((s, z) => s + (z.queue ?? 0), 0)
          : null,
        "neutral",
        "Đơn quầy",
      ),
      kpi(
        "alerts",
        "Cảnh báo",
        homNay.ok ? soCanhBao : null,
        soCanhBao > 0 ? "warn" : "ok",
        "Kho / cảnh báo",
      ),
      kpi(
        "upcoming",
        "Việc trong 15 phút tới",
        homNay.ok ? soViecToi : null,
        "neutral",
        "Việc treo",
      ),
    ];

    // ── Cần xử lý ngay ─────────────────────────────────────────────────────
    const actionsRaw: QuanverseActionItem[] = [];

    // (a) Khu vực vượt ngưỡng tải — nguồn: đơn quầy thật.
    for (const z of zones) {
      if (z.status === "qua_tai") {
        actionsRaw.push({
          id: `zone_${z.zoneId}`,
          severity: "danger",
          title: `${z.label} đang vượt ngưỡng tải`,
          reason:
            z.load !== null && z.threshold !== null
              ? `${z.load} đơn đang xử lý, ngưỡng hiện tại ${z.threshold}.`
              : "Khu vực này đang vượt ngưỡng tải.",
          source: "Đơn quầy",
          at: null,
          ctaLabel: "Xem khu vực",
          ctaHref: null,
        });
      } else if (z.status === "chu_y") {
        actionsRaw.push({
          id: `zone_${z.zoneId}`,
          severity: "warn",
          title: `${z.label} đang gần ngưỡng tải`,
          reason:
            z.load !== null && z.threshold !== null
              ? `${z.load} đơn đang xử lý, ngưỡng ${z.threshold}.`
              : "Tải đang tiến sát ngưỡng.",
          source: "Đơn quầy",
          at: null,
          ctaLabel: null,
          ctaHref: null,
        });
      }
    }

    // (b) Ca thiếu người — nguồn: lịch tuần thật.
    for (const ca of mangHoacRong(lich.data?.ca as readonly CaTho[])) {
      const caId = typeof ca.id === "string" ? ca.id : "";
      if (!caId) continue;
      const toiThieu = soHoacNull(ca.so_nguoi_toi_thieu);
      if (toiThieu === null || toiThieu <= 0) continue;
      const phanCong = ((lich.data?.phan_cong ?? {}) as Record<string, unknown>)[caId];
      const coNguoi = mangHoacRong(phanCong as readonly unknown[]).length;
      if (coNguoi >= toiThieu) continue;
      actionsRaw.push({
        id: `thieu_${caId}`,
        severity: "warn",
        title: `${String(ca.khung ?? ca.vi_tri ?? "Ca")} thiếu ${toiThieu - coNguoi} người`,
        reason: `Định biên ${toiThieu} người, hiện có ${coNguoi}.`,
        source: "Lịch tuần",
        at: null,
        ctaLabel: "Xem phân công",
        ctaHref: "/lich-tuan",
      });
    }

    // (c) Cảnh báo tồn kho — nguồn: kho thật.
    for (const hang of mangHoacRong(homNay.data?.canh_bao_ton as readonly unknown[])) {
      const ten = typeof hang === "string" ? hang : String(hang);
      actionsRaw.push({
        id: `ton_${ten}`,
        severity: "warn",
        title: `${ten} dưới ngưỡng tồn`,
        reason: "Nguyên liệu đã xuống dưới ngưỡng cảnh báo của quán.",
        source: "Kho",
        at: null,
        ctaLabel: "Xem tiêu thụ",
        ctaHref: "/tieu-thu",
      });
    }

    // (d) Việc treo quá hạn — nguồn: hàng đợi việc treo thật.
    for (const t of mangHoacRong(homNay.data?.treo_preview as readonly ViecTho[])) {
      const trangThai = typeof t.trang_thai === "string" ? t.trang_thai : "";
      if (trangThai !== "qua_han") continue;
      const id = typeof t.id === "string" ? t.id : "treo";
      actionsRaw.push({
        id: `treo_${id}`,
        severity: "danger",
        title: "Việc treo quá hạn",
        reason: String(t.noi_dung ?? "Việc kẹt từ ca trước cần xử lý."),
        source: "Việc treo",
        at: null,
        ctaLabel: "Mở việc treo",
        ctaHref: "/treo",
      });
    }

    const actions = chuanHoaActions(actionsRaw).slice(0, 8);

    // ── Timeline 15 phút tới ───────────────────────────────────────────────
    const timeline = chuanHoaTimeline(
      mangTho(snapBody?.next_horizon),
      soHoacNull(stationsBody?.gio) ?? gio,
    );

    // ── Năng lực / dự báo ──────────────────────────────────────────────────
    const forecastBody = forecast.data;
    const capacity = chuanHoaCapacity(
      mangTho(forecastBody?.series),
      forecastBody?.co_du_lieu === true,
      forecastBody?.so_ngay_du_lieu,
      mangTho(forecastBody?.giao_dich_nhat),
    );
    // AI FORECAST — gắn nhãn ảnh hưởng thời tiết (không đổi số nhu cầu).
    const tt = thoiTiet.data;
    if (tt?.co_du_lieu === true) {
      const tomTat =
        typeof tt.anh_huong_quan?.tom_tat === "string" ? tt.anh_huong_quan.tom_tat.trim() : "";
      const moTa = typeof tt.hien_tai?.mo_ta === "string" ? tt.hien_tai.mo_ta.trim() : "";
      capacity.weatherHint = tomTat || (moTa ? `Điều chỉnh theo thời tiết: ${moTa}` : null);
    }

    // ── Sự kiện ────────────────────────────────────────────────────────────
    const events = chuanHoaEvents(mangTho(snapBody?.events), zoneLabelById);

    // ── Chất lượng dữ liệu ─────────────────────────────────────────────────
    const dataQuality = chuanHoaDataQuality(snapBody?.data_quality);
    for (const p of provenance) {
      if (!p.ok) {
        dataQuality.push({
          code: "nguon_loi",
          level: "warning",
          message: `Không đọc được ${p.label}${
            p.status ? ` (HTTP ${p.status})` : ""
          } — phần dữ liệu tương ứng hiển thị "—".`,
        });
      }
    }

    // ── Header ─────────────────────────────────────────────────────────────
    const header = chuanHoaHeader({
      storeName: "Nhịp Quán",
      dateISO: new Date().toISOString().slice(0, 10),
      shiftLabel: nguoiTruc.shiftLabel,
      onShiftNames: nguoiTruc.names,
      onShiftCount:
        nguoiTruc.count ?? (coDonThat ? soHoacNull(chiSo.nhan_su_trong_ca) : null),
      systemStatus: actions.some((a) => a.severity === "danger")
        ? "Có điểm cần xử lý"
        : actions.length > 0
          ? "Theo dõi"
          : "Bình thường",
      updatedAt: typeof snapBody?.generated_at === "string" ? snapBody.generated_at : null,
    });

    // ── AI copilot ─────────────────────────────────────────────────────────
    const copilot = chuanHoaCopilot(
      (brief.data ?? null) as BriefTho | null,
      null,
      "Chưa có tóm tắt cho trạng thái hiện tại.",
    );


    return {
      dataSource: "real",
      scenario: null,
      scenarioLabel: null,
      role: (typeof snapBody?.role === "string" ? snapBody.role : role) as QuanverseRole,
      header,
      kpis,
      zones,
      actions,
      timeline,
      capacity,
      copilot,
      events,
      dataQuality,
      provenance,
    };
  }
}
