/**
 * Nhãn tiếng Việt cho các mã enum của Grand AI Experience.
 *
 * Quy tắc dự án (design-guidelines §Disclosure): mọi mã trạng thái nội bộ phải
 * qua bảng nhãn — không in `draft`, `granted`, `rescue_case`… trực tiếp lên UI.
 * Module này là bản sao pattern của `lib/present.ts` (pick an toàn, fallback =
 * mã gốc chỉ khi lạ hoàn toàn — không bịa nhãn).
 */

export type Tone = "ok" | "warn" | "danger" | "default";

function pick(map: Record<string, string>, code: unknown, fallback: string): string {
  const key = typeof code === "string" ? code : "";
  return map[key] ?? fallback;
}

/** Mã trạng thái đề xuất (ExperienceProposalStatus). */
const PROPOSAL_LABELS: Record<string, string> = {
  draft: "Bản nháp",
  ready: "Sẵn sàng",
  confirmed: "Đã xác nhận",
  rejected: "Bị từ chối",
  expired: "Hết hạn",
};
export function proposalStatusLabel(code: unknown): string {
  return pick(PROPOSAL_LABELS, code, code === null || code === undefined ? "" : String(code));
}

/** Trạng thái đồng thuận ký ức. */
const CONSENT_LABELS: Record<string, string> = {
  required: "Cần đồng thuận",
  granted: "Đã đồng thuận",
  revoked: "Đã thu hồi",
  expired: "Đã hết hạn",
};
export function consentStatusLabel(code: unknown): string {
  return pick(CONSENT_LABELS, code, String(code));
}

/** Phạm vi hiển thị ký ức. */
const VISIBILITY_LABELS: Record<string, string> = {
  private: "Riêng tư",
  staff: "Nhóm nội bộ",
  manager: "Quản lý",
  public: "Công khai",
};
export function visibilityLabel(code: unknown): string {
  return pick(VISIBILITY_LABELS, code, String(code));
}

/** Trạng thái ký ức (status). */
const MEMORY_STATUS_LABELS: Record<string, string> = {
  draft: "Chờ xác nhận",
  confirmed: "Đã xác nhận",
  superseded: "Bị thay thế",
  deleted: "Đã xoá",
};
export function memoryStatusLabel(code: unknown): string {
  return pick(MEMORY_STATUS_LABELS, code, String(code));
}

/**
 * Trạng thái luật trong vòng đời 8 bước của cẩm nang.
 *
 * Phải có bảng riêng vì `proposalStatusLabel` không chứa các mã này — thiếu nó
 * thì UI in thẳng `qua_vf_rule` / `cho_chu_quan` ra màn hình.
 */
const PLAYBOOK_STATUS_LABELS: Record<string, string> = {
  de_xuat: "Bản đề xuất",
  draft: "Bản đề xuất",
  qua_vf_rule: "Đã qua kiểm chứng",
  loai: "Bị loại ở bước kiểm chứng",
  du_tap_su: "Đã đủ tập sự",
  truot_tap_su: "Chưa đạt tập sự",
  cho_chu_quan: "Chờ chủ quán chốt",
  hieu_luc: "Đang hiệu lực",
  tu_tat: "Tự tắt vì sai nhiều",
  da_go: "Đã thu hồi",
};
export function playbookStatusLabel(code: unknown): string {
  return pick(PLAYBOOK_STATUS_LABELS, code, String(code));
}

/** Trạng thái ca cứu hộ. */
const RESCUE_STATUS_LABELS: Record<string, string> = {
  reported: "Đã báo vắng",
  resolving: "Đang xác định ca",
  candidates_ready: "Đã có danh sách người bù",
  proposed: "Đã đề xuất",
  invited: "Đã gửi lời mời",
  responded: "Đã nhận phản hồi",
  confirmed: "Đã xác nhận",
  expired: "Hết hạn",
  cancelled: "Đã huỷ",
};
export function rescueStatusLabel(code: unknown): string {
  return pick(RESCUE_STATUS_LABELS, code, String(code));
}

/** Loại sự kiện trên Living Map. */
const EVENT_TYPE_LABELS: Record<string, string> = {
  incident: "Sự cố",
  process: "Quy trình",
  voice_note: "Ghi chú thoại",
  praise: "Lời khen",
  operation_memory: "Ký ức vận hành",
  decision: "Quyết định",
  mode_change: "Chế độ",
  proposal_confirmed: "Đã duyệt đề xuất",
  proposal_rejected: "Từ chối đề xuất",
  anchor_status: "Trạng thái khu vực",
  rescue_case: "Cứu ca",
  signal: "Tín hiệu",
  mode_proposal: "Đề xuất chế độ",
  event: "Sự kiện",
};
export function eventTypeLabel(code: unknown): string {
  return pick(EVENT_TYPE_LABELS, code, String(code));
}

/** Trạng thái sự kiện công khai. */
const EVENT_STATUS_LABELS: Record<string, string> = {
  proposed: "Đang chờ duyệt",
  draft: "Bản nháp",
  ready: "Sẵn sàng",
  confirmed: "Đã xác nhận",
  candidates_ready: "Đang chờ chọn người",
  done: "Hoàn tất",
  closed: "Đã đóng",
};
export function eventStatusLabel(code: unknown): string {
  return pick(EVENT_STATUS_LABELS, code, String(code));
}

/** Loại mục tầm nhìn 15 phút. */
const HORIZON_KIND_LABELS: Record<string, string> = {
  event: "Sự kiện",
  signal: "Tín hiệu",
  handover: "Bàn giao",
  mode_proposal: "Đề xuất chế độ",
};
export function horizonKindLabel(code: unknown): string {
  return pick(HORIZON_KIND_LABELS, code, String(code));
}

/** Chế độ quán. */
const MODE_LABELS: Record<string, string> = {
  troi_mua: "Trời mưa",
  gio_cao_diem: "Giờ cao điểm",
  khach_doan: "Khách đoàn",
  thieu_nhan_su: "Thiếu nhân sự",
  quan_yen_tinh: "Quán yên tĩnh",
  dem_nhac: "Đêm nhạc",
};
export function modeLabel(code: unknown): string {
  return pick(MODE_LABELS, code, String(code));
}

/** Kết quả xác nhận proposal. */
export function confirmOutcomeLabel(ok: boolean): string {
  return ok ? "Đã xác nhận" : "Không xác nhận";
}

/** Reason code eligibility (Shift Rescue) → tiếng Việt. */
const ELIGIBILITY_REASON_LABELS: Record<string, string> = {
  C01: "Trùng giờ học (TKB)",
  C02: "Thiếu kỹ năng vị trí",
  C03: "Trùng ca cùng lúc",
  C04: "Chưa đủ giờ nghỉ tối thiểu",
  C05: "Vượt trần giờ tuần",
  C06: "Đang nghỉ phép đã duyệt",
  SKILL: "Thiếu kỹ năng",
  CAP: "Vượt trần giờ",
  SELF: "Không thể thay chính mình",
  thieu_ky_nang: "Thiếu kỹ năng vị trí",
  vuot_tran_gio: "Vượt trần giờ tuần",
  hard_constraints_ok: "Đạt mọi ràng buộc cứng",
};
export function eligibilityReasonLabel(code: unknown): string {
  const key = typeof code === "string" ? code.toUpperCase() : "";
  if (key in ELIGIBILITY_REASON_LABELS) return ELIGIBILITY_REASON_LABELS[key];
  return pick(ELIGIBILITY_REASON_LABELS, code, String(code));
}

/** Priority pass reason (dạng "fairness_delta=1.20") → tách nhãn gọn. */
export function passReasonLabel(text: string): string {
  if (text.startsWith("fairness_delta=")) return `Chênh lệch công bằng ${Number(text.split("=")[1]).toFixed(2)}`;
  if (text.startsWith("added_hours=")) return `Thêm ${text.split("=")[1]} giờ`;
  if (text.startsWith("policy_version=")) return `Chính sách ${text.split("=")[1]}`;
  return eligibilityReasonLabel(text);
}

/** Tên lựa chọn War Room từ option_id (vd opt_crisis_rain_scn → Mưa lớn). */
export function warOptionTitle(optionId: string, fallback: string): string {
  if (optionId.includes("crisis_rain")) return "Mưa lớn";
  if (optionId.includes("crisis_peak") || optionId.includes("demand")) return "Giờ cao điểm";
  if (optionId.includes("crisis_short") || optionId.includes("staff")) return "Thiếu nhân sự";
  if (optionId.includes("crisis_outage") || optionId.includes("equipment")) return "Thiết bị hỏng";
  if (optionId.includes("crisis_group") || optionId.includes("large")) return "Khách đoàn";
  return fallback;
}

/** Loại nguồn. */
const SOURCE_LABELS: Record<string, string> = {
  replay: "Fixture replay",
  user: "Người dùng",
  system: "Hệ thống",
  agent: "Trợ lý AI",
};
export function sourceLabel(code: unknown): string {
  return pick(SOURCE_LABELS, code, String(code));
}

/** Kênh dự phòng của AR-lite khi thiết bị không mở được camera. */
const AR_FALLBACK_LABELS: Record<string, string> = {
  map_or_qr_text: "mở bản đồ hoặc quét mã QR kèm chữ",
  none: "không cần dự phòng",
  text: "chỉ hiện chữ hướng dẫn",
  map: "chuyển sang bản đồ 2D",
};
export function arFallbackLabel(code: unknown): string {
  return pick(AR_FALLBACK_LABELS, code, String(code));
}

/** Vị trí làm việc trong ca — dùng ở Shift Rescue và bảng xếp người. */
const POSITION_LABELS: Record<string, string> = {
  pha_che: "Pha chế",
  phuc_vu: "Phục vụ",
  thu_ngan: "Thu ngân",
  bep: "Bếp",
  bar: "Bar",
  tap_vu: "Tạp vụ",
};
export function positionLabel(code: unknown): string {
  return pick(POSITION_LABELS, code, String(code));
}

/** Buổi trong ngày của ca. */
const DAY_PART_LABELS: Record<string, string> = {
  sang: "sáng",
  chieu: "chiều",
  toi: "tối",
  dem: "đêm",
};
export function dayPartLabel(code: unknown): string {
  return pick(DAY_PART_LABELS, code, String(code));
}

/** Thứ trong tuần dạng nhãn đọc được (giữ nguyên nếu đã là "T7", "CN"). */
const WEEKDAY_LABELS: Record<string, string> = {
  T2: "Thứ Hai",
  T3: "Thứ Ba",
  T4: "Thứ Tư",
  T5: "Thứ Năm",
  T6: "Thứ Sáu",
  T7: "Thứ Bảy",
  CN: "Chủ nhật",
};
export function weekdayLabel(code: unknown): string {
  return pick(WEEKDAY_LABELS, code, String(code));
}

/**
 * Câu luật do máy sinh còn ở dạng mã (`day_part = toi, demand_band = cao…`).
 *
 * Người quản lý phải đọc được câu luật trước khi ban hành; để nguyên mã thì
 * "ban hành" là quyết định mù. Hàm này dịch các cặp `khoá = giá_trị` sang câu
 * tiếng Việt, giữ nguyên phần nào không nhận ra để không bịa nghĩa.
 */
const CONDITION_KEYS: Record<string, string> = {
  day_part: "buổi",
  demand_band: "mức cầu",
  skill: "kỹ năng",
  station: "vị trí",
  thu: "thứ",
  khung: "buổi",
  vi_tri: "vị trí",
  so_nguoi: "số người",
  nguong: "ngưỡng",
  ma_buoc: "bước",
  thang_kinh_nghiem: "tháng kinh nghiệm",
};
const CONDITION_VALUES: Record<string, string> = {
  // buổi
  toi: "tối",
  sang: "sáng",
  chieu: "chiều",
  dem: "đêm",
  // mức cầu
  cao: "cao",
  vua: "vừa",
  thap: "thấp",
  // vị trí / kỹ năng
  pha_che: "pha chế",
  phuc_vu: "phục vụ",
  thu_ngan: "thu ngân",
  bar: "quầy bar",
  bep: "bếp",
  // thứ
  T2: "Thứ Hai",
  T3: "Thứ Ba",
  T4: "Thứ Tư",
  T5: "Thứ Năm",
  T6: "Thứ Sáu",
  T7: "Thứ Bảy",
  CN: "Chủ nhật",
};
/**
 * Hành động kết luận của luật (`them_nguoi_gio_cao_diem`…) → câu tiếng Việt.
 *
 * Tách khỏi vế điều kiện vì đây là phần SAU "thì" — gộp chung một biểu thức
 * thay thế thì câu ra sai ngữ pháp.
 */
const ACTION_LABELS: Record<string, string> = {
  them_nguoi_gio_cao_diem: "thêm người cho giờ cao điểm",
  them_nguoi: "thêm người cho ca",
  bot_nguoi: "giảm người ở ca",
  doi_nguoi: "đổi người giữa các ca",
  giu_nguyen: "giữ nguyên định biên",
  uu_tien_ky_nang: "ưu tiên người đúng kỹ năng",
  san_ca: "san người giữa các ca",
  ghep_ky_nang: "ghép người theo kỹ năng",
  nhu_cau_ca: "xếp theo nhu cầu của ca",
};
export function ruleActionLabel(code: unknown): string {
  return pick(ACTION_LABELS, code, String(code));
}

export function ruleSentenceLabel(sentence: unknown): string {
  if (typeof sentence !== "string" || !sentence.trim()) return String(sentence ?? "");
  // Vế điều kiện: dịch từng cặp `khoá = giá_trị`.
  const withConditions = sentence.replace(
    /([a-z_]+)\s*=\s*([A-Za-z0-9_À-ỹ]+)/g,
    (whole, key: string, value: string) => {
      const k = CONDITION_KEYS[key];
      const v = CONDITION_VALUES[value];
      if (!k) return whole; // khoá lạ: giữ nguyên, không đoán
      return `${k} ${v ?? value}`;
    },
  );
  // Vế kết luận: mã hành động sau "thì" phải thành câu, không để `them_nguoi…`.
  return withConditions.replace(
    /\bthì\s+([a-z_]+)/g,
    (whole, action: string) => {
      const label = ACTION_LABELS[action];
      return label ? `thì ${label}` : whole;
    },
  );
}

/** Loại khu vực trên Living Map. */
const ZONE_KIND_LABELS: Record<string, string> = {
  quay: "Quầy",
  phong_khach: "Khu khách",
  loi_vao: "Lối vào",
  kho: "Kho",
  ve_sinh: "Vệ sinh",
};
export function zoneKindLabel(code: unknown): string {
  return pick(ZONE_KIND_LABELS, code, String(code));
}

/** Mức chất lượng dữ liệu của snapshot. */
const DATA_LEVEL_LABELS: Record<string, string> = {
  info: "Thông tin",
  // Hợp đồng `DataQualityNotice.level` dùng `warning`, KHÔNG phải `warn`.
  // Thiếu khoá này thì UI in thẳng chữ "warning" ra màn hình (vi phạm quy tắc
  // mã nội bộ phải qua bảng nhãn) — đúng lỗi đã có ở đây.
  warning: "Cần lưu ý",
  warn: "Cần lưu ý",
  error: "Thiếu dữ liệu",
  debug: "Kỹ thuật",
  ok: "Đầy đủ",
};
export function dataQualityLevelLabel(code: unknown): string {
  return pick(DATA_LEVEL_LABELS, code, String(code));
}

/** Mã chất lượng dữ liệu → câu người đọc được. */
const DATA_CODE_LABELS: Record<string, string> = {
  fixture_replay: "Đang chạy dữ liệu diễn tập",
  public_mode: "Bản chiếu khách — không kèm dữ liệu vận hành",
  stale_snapshot: "Ảnh trạng thái đã cũ",
  rate_limited: "Đã chạm trần truy vấn",
  missing_horizon: "Chưa có tầm nhìn 15 phút",
};
export function dataQualityLabel(code: unknown): string {
  return pick(DATA_CODE_LABELS, code, String(code));
}

/** Điểm của một khu vực trên Living Map (tải thấp/vừa/cao). */
export function zoneLoadLabel(load: unknown): string {
  const n = typeof load === "number" ? load : Number(load);
  if (!Number.isFinite(n)) return "Không rõ tải";
  const pct = Math.round(n * 100);
  if (n >= 0.7) return `Tải cao ${pct}%`;
  if (n >= 0.4) return `Tải vừa ${pct}%`;
  return `Tải nhẹ ${pct}%`;
}