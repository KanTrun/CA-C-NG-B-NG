/**
 * QUÁNVERSE — hợp đồng dữ liệu CHUẨN cho trung tâm điều hành quán.
 *
 * Đây là MỘT hình dạng duy nhất mà UI biết. Nguồn thật (`RealQuanverseRepository`)
 * và nguồn mô phỏng (`MockQuanverseRepository`) đều phải trả về đúng hình dạng
 * này, nên UI không bao giờ viết hai lần và không bao giờ `import` mock trực tiếp.
 *
 * ─── QUY ƯỚC SỐ (bắt buộc, không được vi phạm) ───────────────────────────────
 *
 *   `null`  = CHƯA CÓ DỮ LIỆU  → UI hiển thị "—"  (hoặc "Chưa có dữ liệu")
 *   `0`     = CÓ dữ liệu và giá trị bằng không → UI hiển thị "0"
 *
 * Tuyệt đối không được suy `null` thành `0`. Đây là quy ước đã dùng ở hợp đồng
 * hao hụt (`ca_contracts/loss.py`: `None` = chưa có dữ liệu, `0.0` = có và bằng
 * không) — giữ nhất quán toàn hệ thống.
 *
 * Vì vậy MỌI trường số ở đây đều `number | null` khi giá trị vắng mặt là chuyện
 * thường ngày (chưa có đơn, chưa đủ lịch sử, nguồn lỗi). Trường luôn có (ví dụ
 * số khu vực đã biết) mới để `number`.
 */

export type QuanverseRole = "khach" | "nhan_vien" | "quan_ly" | "chu_quan";

/** Nguồn của cả màn: đọc API thật, hay fixture mô phỏng. */
export type QuanverseDataSource = "real" | "mock";

/**
 * Kịch bản mô phỏng. Khai ở hợp đồng (không ở tầng đọc) để UI tham chiếu được
 * mà không phải import từ `repository/`.
 */
export type QuanverseScenario = "binh_thuong" | "cao_diem" | "qua_tai_pha";

// ── Truy xuất nguồn (data provenance) ───────────────────────────────────────

/** Một nguồn dữ liệu đã gọi để dựng màn này. */
export interface QuanverseProvenance {
  /** Nhãn đọc được, ví dụ "Tải theo khu vực". */
  label: string;
  /** Đường dẫn API đã gọi (rút gọn, không kèm query). */
  endpoint: string;
  /** Gọi có thành công không. `false` ⇒ các trường của nguồn này là null. */
  ok: boolean;
  /** Mã lỗi HTTP nếu thất bại (0 = lỗi mạng). */
  status?: number;
  /** Các trường không lấy được từ nguồn này. */
  missingFields?: string[];
}

// ── A. HEADER — tình trạng quán ─────────────────────────────────────────────

export interface QuanverseStoreHeader {
  storeName: string;
  /** ISO date (YYYY-MM-DD) của ngày vận hành. Không hard-code. */
  dateISO: string;
  /** Nhãn ca hiện tại, ví dụ "14:00–18:00". `null` khi không khớp ca nào. */
  shiftLabel: string | null;
  /** Tên nhân sự đang trực. Mảng rỗng = chưa suy ra được tên (khác null). */
  onShiftNames: string[];
  /** Số nhân sự đang trực. `null` khi nguồn không cho biết. */
  onShiftCount: number | null;
  /** Nhãn trạng thái hệ thống, ví dụ "Bình thường". */
  systemStatus: string;
  /** Thời điểm dữ liệu cập nhật gần nhất (ISO). `null` nếu nguồn không nói. */
  updatedAt: string | null;
}

// ── B. EXECUTIVE SNAPSHOT — sáu KPI ────────────────────────────────────────

export type QuanverseKpiTone = "neutral" | "ok" | "warn" | "danger";

/** Một ô KPI. `value === null` ⇒ hiện "—" + "Chưa có dữ liệu". */
export interface QuanverseKpi {
  key: "staff" | "zones" | "orders" | "queue" | "alerts" | "upcoming";
  label: string;
  value: number | null;
  unit?: string;
  tone: QuanverseKpiTone;
  /** Nguồn của con số này (nhãn đọc được). */
  source: string;
}

// ── C. TRẠNG THÁI KHU VỰC — bản đồ vận hành ─────────────────────────────────

export type QuanverseZoneStatus =
  | "on_dinh"
  | "chu_y"
  | "qua_tai"
  | "chua_co_du_lieu";

export interface QuanverseZoneAlert {
  severity: QuanverseKpiTone;
  message: string;
}

export interface QuanverseZone {
  zoneId: string;
  label: string;
  kind: string;
  status: QuanverseZoneStatus;
  /** Tải hiện tại (đơn đang xử lý). */
  load: number | null;
  /** Ngưỡng tải để so. `null` khi nguồn không khai ngưỡng. */
  threshold: number | null;
  /** Đơn đang chờ. */
  queue: number | null;
  /** Số nhân sự được phân cho khu vực. */
  assignedStaff: number | null;
  /** Tên người phụ trách, nếu suy ra được. */
  assignedNames: string[];
  alerts: QuanverseZoneAlert[];
}

// ── D. CẦN XỬ LÝ NGAY ──────────────────────────────────────────────────────

export interface QuanverseActionItem {
  id: string;
  severity: QuanverseKpiTone;
  title: string;
  /** Vì sao mục này xuất hiện. */
  reason: string;
  /** Nhãn nguồn dữ liệu ("Đơn quầy", "SOP", "Lịch tuần"…). */
  source: string;
  /** Thời điểm gắn với mục (ISO) hoặc `null` khi không có mốc. */
  at: string | null;
  /** Nhãn hành động gợi ý; `null` khi không có đường đi rõ ràng. */
  ctaLabel: string | null;
  /** Đường dẫn nội bộ để mở. `null` khi CTA chỉ là thông tin. */
  ctaHref: string | null;
}

// ── E. 15 PHÚT TỚI — timeline vận hành ─────────────────────────────────────

export type QuanverseTimelineStatus = "sap_toi" | "dang_chay" | "xong" | "qua_han";

export interface QuanverseTimelineItem {
  id: string;
  /** ISO datetime hoặc chuỗi "HH:MM" khi nguồn chỉ có giờ. */
  at: string;
  title: string;
  kind: string;
  source: string;
  status: QuanverseTimelineStatus;
  /** Khu vực gắn mốc (nếu nguồn có). `null` = toàn quán. */
  zoneId?: string | null;
}

// ── F. NĂNG LỰC / TẢI VẬN HÀNH ─────────────────────────────────────────────

export interface QuanverseCapacityPoint {
  /** Giờ vận hành 7..22. */
  hour: number;
  /** Nhu cầu dự báo. `null` khi chưa đủ lịch sử. */
  demand: number | null;
  /** Hàng chờ dự báo. `null` khi chưa đủ lịch sử. */
  backlog: number | null;
}

export interface QuanverseCapacity {
  points: QuanverseCapacityPoint[];
  /** Có đủ lịch sử để vẽ không. `false` ⇒ UI nói thẳng "chưa đủ dữ liệu". */
  hasHistory: boolean;
  /** Số ngày dữ liệu đã dùng. `null` khi nguồn không cho biết. */
  daysOfData: number | null;
  /** Các giờ cao điểm theo dữ liệu. */
  peaks: number[];
  /**
   * Gợi ý điều chỉnh theo thời tiết (AI FORECAST). Không đổi số nhu cầu —
   * chỉ nhãn để người đọc biết tín hiệu môi trường. `null` khi chưa có thời tiết.
   */
  weatherHint: string | null;
  /** Mode đề xuất từ thời tiết (vd `troi_mua`). `null` khi không đề xuất. */
  weatherSuggestMode: string | null;
  weatherSuggestModeLabel: string | null;
  /** Thiếu GPS/địa chỉ — UI hiện CTA lấy vị trí. */
  weatherNeedsLocation: boolean;
}

// ── G. AI COPILOT ──────────────────────────────────────────────────────────

/**
 * Kết quả AI copilot. KHÔNG có trường `confidence` số vì backend hiện KHÔNG
 * trả về (chỉ có `grounded: boolean`) — hợp đồng không được bịa ra thứ backend
 * không có. Khi backend bổ sung, thêm `confidence?: number | null` tại đây.
 */
export interface QuanverseCopilot {
  headline: string;
  /** Lý do / diễn giải. */
  reasons: string[];
  /** Nguồn hậu thuẫn (trích dẫn). Rỗng ⇒ UI nói "Chưa có bản ghi hậu thuẫn." */
  citations: string[];
  /** Những câu AI KHÔNG có căn cứ. */
  unsupportedClaims: string[];
  grounded: boolean;
  /** `"replay"` = tất định, khác = tên nhà cung cấp LLM. */
  provider: string;
  /** Hành động gợi ý (chỉ đề xuất — không bao giờ tự ghi DB). */
  suggestedActions: string[];
}

// ── H. SỰ KIỆN VẬN HÀNH ────────────────────────────────────────────────────

export interface QuanverseEvent {
  id: string;
  type: string;
  /** Nhãn tiếng Việt của `type`. */
  typeLabel: string;
  status: string;
  /** ISO datetime hoặc nhãn thời gian tương đối khi nguồn chỉ có mốc lệch. */
  occurredAt: string;
  /** Nhãn nguồn. */
  source: string;
  sourceLabel: string;
  summary: string;
  zoneId: string | null;
  /** Nhãn khu vực (đã tra) hoặc "Toàn quán". */
  zoneLabel: string;
}

// ── Gốc ────────────────────────────────────────────────────────────────────

export interface QuanverseViewModel {
  dataSource: QuanverseDataSource;
  /** Kịch bản mô phỏng; `null` ở chế độ thật. */
  scenario: QuanverseScenario | null;
  /** Nhãn kịch bản đọc được; `null` ở chế độ thật. */
  scenarioLabel: string | null;
  /** Vai trò mà MÁY CHỦ đã cắt dữ liệu theo. */
  role: QuanverseRole;
  header: QuanverseStoreHeader;
  kpis: QuanverseKpi[];
  zones: QuanverseZone[];
  actions: QuanverseActionItem[];
  timeline: QuanverseTimelineItem[];
  capacity: QuanverseCapacity;
  copilot: QuanverseCopilot | null;
  events: QuanverseEvent[];
  /** Ghi chú chất lượng dữ liệu từ máy chủ, cộng ghi chú của tầng đọc. */
  dataQuality: QuanverseDataQualityNotice[];
  /** Mọi nguồn đã gọi, kèm trạng thái thành/bại. */
  provenance: QuanverseProvenance[];
}

export interface QuanverseDataQualityNotice {
  code: string;
  level: "info" | "warning" | "error";
  message: string;
}

// ── AI Ask (kết quả một lần hỏi) ───────────────────────────────────────────

/** Kết quả `POST /ask` — tách khỏi brief tĩnh để UI giữ cả hai. */
export interface QuanverseAskResult {
  question: string;
  answer: string;
  citations: string[];
  unsupportedClaims: string[];
  grounded: boolean;
  provider: string;
}

// ── Cafe Modes (đề xuất → xác nhận) ────────────────────────────────────────

export type QuanverseModeStatus = "off" | "draft" | "active";

export interface QuanverseMode {
  mode: string;
  label: string;
  active: boolean;
  proposalStatus: string;
  status: QuanverseModeStatus;
  effect: string;
  affectedProjections: string[];
}

export interface QuanverseModesState {
  modes: QuanverseMode[];
  canActivate: boolean;
  role: QuanverseRole;
}

// ── Selection helpers (con trỏ hệ thống) ───────────────────────────────────

/** Lấy zoneId từ action id dạng `zone_<id>`; null nếu không gắn khu vực. */
export function zoneIdTuAction(action: QuanverseActionItem): string | null {
  if (action.id.startsWith("zone_")) return action.id.slice("zone_".length);
  return null;
}

/** Lọc actions theo khu vực đang chọn — giữ mục toàn quán (không gắn zone). */
export function locActionsTheoZone(
  actions: readonly QuanverseActionItem[],
  zoneId: string | null,
): QuanverseActionItem[] {
  if (!zoneId) return [...actions];
  return actions.filter((a) => {
    const z = zoneIdTuAction(a);
    return z === null || z === zoneId;
  });
}

/** Lọc events theo khu vực — mục không gắn zone vẫn hiện. */
export function locEventsTheoZone(
  events: readonly QuanverseEvent[],
  zoneId: string | null,
): QuanverseEvent[] {
  if (!zoneId) return [...events];
  return events.filter((e) => e.zoneId === null || e.zoneId === zoneId);
}

/** Lọc timeline theo khu vực khi nguồn có `zoneId`. */
export function locTimelineTheoZone(
  items: readonly QuanverseTimelineItem[],
  zoneId: string | null,
): QuanverseTimelineItem[] {
  if (!zoneId) return [...items];
  const coZone = items.some((i) => i.zoneId);
  if (!coZone) return [...items];
  return items.filter((i) => !i.zoneId || i.zoneId === zoneId);
}

/** Zone nóng nhất (quá tải > chú ý) — dùng khi bấm KPI alerts/queue. */
export function zoneNongNhat(zones: readonly QuanverseZone[]): string | null {
  const quaTai = zones.find((z) => z.status === "qua_tai");
  if (quaTai) return quaTai.zoneId;
  const chuY = zones.find((z) => z.status === "chu_y");
  return chuY?.zoneId ?? null;
}

// ── Hàm hiển thị dùng CHUNG (một chỗ duy nhất cho quy ước null) ────────────

export const KHONG_CO_DU_LIEU = "—";
export const CHUA_CO_DU_LIEU = "Chưa có dữ liệu";

/**
 * Định dạng một giá trị số cho UI, tôn trọng quy ước `null`.
 *
 * Đây là CHỐT DUY NHẤT chống "biến null thành 0": mọi chỗ render số trong
 * Quánverse phải đi qua hàm này. Nhận cả `null`, `undefined`, `NaN` và `""`
 * (backend có thể trả chuỗi rỗng) — tất cả đều ra "—", không bao giờ ra "0".
 */
export function formatSo(
  value: number | string | null | undefined,
  opts: { decimals?: number; unit?: string } = {},
): string {
  if (value === null || value === undefined) return KHONG_CO_DU_LIEU;
  if (typeof value === "string" && !value.trim()) return KHONG_CO_DU_LIEU;
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n) || !Number.isFinite(n)) return KHONG_CO_DU_LIEU;
  const text = opts.decimals !== undefined ? n.toFixed(opts.decimals) : String(n);
  return opts.unit ? `${text} ${opts.unit}` : text;
}

/**
 * Chuẩn hoá giá trị thô từ API về `number | null`.
 *
 * Dùng ở mọi adapter. Bảo vệ trước trường thiếu, `undefined`, chuỗi rỗng và
 * chuỗi không phải số — tất cả đều thành `null` (CHƯA CÓ DỮ LIỆU), KHÔNG thành 0.
 */
export function soHoacNull(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string") {
    // Chuỗi RỖNG hoặc chỉ khoảng trắng KHÔNG phải số — `Number("  ")` trả 0
    // nên phải chặn trước khi ép kiểu, không thì ô "chưa có dữ liệu" thành "0".
    const trimmed = value.trim();
    if (!trimmed) return null;
    const n = Number(trimmed);
    return Number.isFinite(n) ? n : null;
  }
  // Mọi kiểu khác (mảng, object, boolean, null, undefined) đều KHÔNG phải số.
  // `Number([])` = 0 và `Number(true)` = 1 — cả hai đều là "0 giả" nếu lọt qua.
  return null;
}

/** Mảng thì luôn an toàn — `undefined` thành `[]`, không phải null. */
export function mangHoacRong<T>(value: readonly T[] | null | undefined): T[] {
  return Array.isArray(value) ? [...value] : [];
}

/**
 * Như `mangHoacRong` nhưng nhận giá trị `unknown` (trường thô từ API).
 *
 * Dùng ở adapter khi chưa kiểm kiểu: `unknown` → mảng các `unknown`, không ném.
 */
export function mangTho(value: unknown): unknown[] {
  return Array.isArray(value) ? [...value] : [];
}
