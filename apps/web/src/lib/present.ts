/**
 * Lớp trình bày — chốt kiểm duyệt hiển thị của apps/web.
 *
 * Ba việc, đều là ràng buộc từ `docs/design-guidelines.md`:
 *  1. Lỗi kỹ thuật → câu tiếng Việt người vận hành hiểu, kèm hành động kế tiếp.
 *     Không stack trace, không JSON lỗi, không mã HTTP, không tên biến.
 *  2. Mã trạng thái nội bộ (`cho_duyet`, `ag_msg`, `pin_ca`…) → nhãn tiếng Việt.
 *  3. Giá trị `null`/`undefined`/object → dấu gạch, tuyệt đối không "[object Object]".
 */
import { ApiError } from "./api";

const DASH = "—";

/** Ép mọi giá trị lạ về chuỗi an toàn cho UI. */
export function safeText(value: unknown, fallback = DASH): string {
  if (value == null) return fallback;
  if (typeof value === "string") return value.trim() === "" ? fallback : value;
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : fallback;
  if (typeof value === "boolean") return value ? "có" : "không";
  return fallback;
}

/** Số thực an toàn — dùng cho số dư công bằng, số lượng tồn. */
export function safeNumber(value: unknown, digits = 1): string {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : DASH;
}

export type ErrorCopy = {
  /** Việc đang làm, viết tiếp được sau chữ "không": "đọc được bảng hôm nay". */
  doing: string;
  forbidden?: string;
  missing?: string;
  conflict?: string;
  invalid?: string;
};

/**
 * Đổi lỗi bất kỳ thành một câu tiếng Việt + hành động kế tiếp.
 * Chỉ đọc `status`; không bao giờ đọc `message`, nên không có đường nào để
 * chuỗi kỹ thuật của máy chủ lọt ra UI.
 */
export function viError(err: unknown, copy: ErrorCopy): string {
  const status = err instanceof ApiError ? err.status : -1;
  if (status === 0) {
    return `Chưa nối được máy chủ quán nên không ${copy.doing}. Kiểm tra mạng rồi bấm tải lại.`;
  }
  if (status === 401) {
    return "Phiên làm việc đã hết. Đăng nhập lại rồi làm tiếp.";
  }
  if (status === 403) {
    return copy.forbidden ?? `Bạn không có quyền ${copy.doing}. Nhờ quản lý hoặc chủ quán làm bước này.`;
  }
  if (status === 404) {
    return (
      copy.missing ??
      `Không tìm thấy dữ liệu để ${copy.doing}. Tải lại trang; nếu vẫn trống thì nhắn quản lý kiểm tra dữ liệu quán.`
    );
  }
  if (status === 409) {
    // Nếu là ApiError có detail, dịch mã 409 cụ thể của lịch tuần
    if (err instanceof ApiError && err.detail !== undefined) {
      return lich409Loi(err.detail);
    }
    return copy.conflict ?? "Dữ liệu vừa đổi ở nơi khác. Tải lại trang rồi làm lại từ đầu.";
  }
  if (status === 400 || status === 422) {
    // Máy chủ trả detail là câu tiếng Việt hoàn chỉnh (vd bản thu im lặng của
    // process-audio) thì hiện thẳng — thông báo chung "nhập chưa hợp lệ" vô
    // nghĩa với người không nhập gì cả (gặp thật 2026-10-01). Chỉ nhận câu có
    // dấu tiếng Việt để không lộ chuỗi kỹ thuật tiếng Anh ra UI.
    if (err instanceof ApiError) {
      const detail = err.detail;
      if (
        typeof detail === "string" &&
        /\s/.test(detail.trim()) &&
        /[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộùúủũụỳýỷỹỵ]/i.test(detail)
      ) {
        return detail.trim();
      }
    }
    return copy.invalid ?? "Thông tin nhập chưa hợp lệ. Kiểm tra lại các ô rồi gửi lại.";
  }
  if (status === 429) {
    return "Quá nhiều lượt trong thời gian ngắn. Chờ một phút rồi thử lại.";
  }
  if (status >= 500) {
    return `Máy chủ quán đang lỗi nên không ${copy.doing}. Thử lại sau ít phút, nếu vẫn vậy báo quản lý.`;
  }
  return `Không ${copy.doing}. Tải lại trang rồi thử lại; nếu vẫn vậy báo quản lý.`;
}

/* ── Nhãn người ──
   `nvLabel(id)` cố ý ẩn tên riêng (công bằng / sổ vết).
   Lưới lịch và chọn người dùng `ten` từ API; `nvTenHienThi` chuẩn hóa chuỗi đó. */

/** `nv_03` → "Nhân viên 03". Không in mã nội bộ, không in tên thật. */
export function nvLabel(id?: string | null): string {
  const raw = safeText(id, "");
  if (!raw) return "Nhân viên trong quán";
  const num = raw.match(/(\d+)\s*$/);
  if (num) return `Nhân viên ${num[1]}`;
  if (raw === "quan_ly") return "Quản lý";
  if (raw === "chu_quan") return "Chủ quán";
  if (raw === "nhan_vien") return "Nhân viên";
  return "Nhân viên trong quán";
}

/** Tên trên lưới ca: ưu tiên `ten` từ máy chủ; bỏ dạng placeholder "Nhan Vien 01". */
export function nvTenHienThi(ten: unknown, id?: string | null): string {
  const name = safeText(ten, "");
  if (name && !/^nhan\s*vien\s*\d+$/i.test(name.replace(/\s+/g, " ").trim())) {
    return name;
  }
  return nvLabel(id);
}

/** Thay mọi `nv_01` / `nv_07` trong chuỗi tự do bằng tên hiển thị. */
export function replaceNvIdsInText(
  text: unknown,
  resolveName: (nvId: string) => string,
): string {
  const raw = safeText(text, "");
  if (!raw) return raw;
  return raw.replace(/\bnv_\d+\b/gi, (id) => resolveName(id));
}

/** Nhãn hiển thị cho tên agent (ag_copilot → "AG-COPILOT"). */
const AGENT_LABELS: Record<string, string> = {
  ag_copilot: "AG-COPILOT",
  ag_scheduler: "AG-SCHEDULER",
  ag_mailwriter: "AG-MAILWRITER",
  ag_pricing: "AG-PRICING",
  ag_sop: "AG-SOP",
  ag_tkb: "AG-TKB",
  ag_waste: "AG-WASTE",
  ag_barista: "AG-BARISTA",
  ag_concierge: "AG-CONCIERGE",
  ag_supervisor: "AG-SUPERVISOR",
  ag_meeting: "AG-MEETING",
  ag_msg: "AG-MSG",
  ag_brief: "AG-BRIEF",
  ag_explain: "AG-EXPLAIN",
  ag_handover: "AG-HANDOVER",
  ag_fbpage: "AG-FBPAGE",
  ag_trend: "AG-TREND",
  ag_mail: "AG-MAIL",
  ag_rule: "AG-RULE",
  ag_voc: "AG-VOC",
};

/** Nhãn hiển thị thân thiện cho tên agent; trả về chính tên nếu không biết. */
export function agentNameLabel(agentName?: string | null): string | null {
  const raw = safeText(agentName, "");
  if (!raw) return null;
  return AGENT_LABELS[raw] ?? raw;
}

/** Người thực hiện trong sổ vết: vai trò hoặc nhân viên, không tên riêng.
 *  Giữ lại cho các nơi chưa có danh bạ tải sẵn — ưu tiên dùng `actorLabelEx`. */
export function actorLabel(ai?: string | null): string {
  return actorLabelEx(ai);
}

/**
 * Người thực hiện — dùng tên thật khi có danh bạ (`GET /api/v1/ops/pickers`)
 * qua `resolveName`; không có thì lùi về nhãn vai trò/agent, KHÔNG bao giờ in
 * thẳng `nv_01`. Trang Truy vết, Bàn giao ca, Chợ đổi ca… nên truyền
 * `useStaffNameMap()` vào đây để hiển thị "Lan Nguyễn" thay vì "Nhân viên 01".
 */
export function actorLabelEx(
  ai?: string | null,
  resolveName?: (nvId: string) => string,
): string {
  const raw = safeText(ai, "");
  if (!raw) return "Không rõ người thực hiện";
  if (raw === "quan_ly") return "Quản lý";
  if (raw === "chu_quan") return "Chủ quán";
  if (raw === "nhan_vien") return "Nhân viên";
  if (raw === "system" || raw === "unknown") return "Hệ thống";
  if (raw === "guest" || raw === "nv_guest") return "Khách";
  if (raw === "fb_policy_engine") return "Hệ thống chính sách Facebook";
  if (raw === "fb_moderation_block") return "Hệ thống kiểm duyệt Facebook";
  const agent = AGENT_LABELS[raw];
  if (agent) return agent;
  if (/^nv_\d+$/i.test(raw) && resolveName) {
    const name = resolveName(raw);
    if (name && name !== nvLabel(raw)) return name;
  }
  return nvLabel(raw);
}

/** Nhãn tiếng Việt cho các mã snake_case xuất hiện trong dữ liệu AI tất định
 *  (đề xuất thông minh, giải thích, thử nghiệm an toàn) — thay cho việc in
 *  thẳng `ca_doanh_thu`, `T6_toi`, `tang_gia` ra giao diện. */
const CODE_LABELS: Record<string, string> = {
  ca_doanh_thu: "Ca theo doanh thu",
  lich_su_doanh_thu: "Lịch sử doanh thu",
  tang_gia: "Tăng giá",
  giam_gia: "Giảm giá",
  tang_ns: "Tăng nhân sự",
  giam_ns: "Giảm nhân sự",
  T2_sang: "Sáng Thứ 2",
  T2_chieu: "Chiều Thứ 2",
  T2_toi: "Tối Thứ 2",
  T3_sang: "Sáng Thứ 3",
  T3_chieu: "Chiều Thứ 3",
  T3_toi: "Tối Thứ 3",
  T4_sang: "Sáng Thứ 4",
  T4_chieu: "Chiều Thứ 4",
  T4_toi: "Tối Thứ 4",
  T5_sang: "Sáng Thứ 5",
  T5_chieu: "Chiều Thứ 5",
  T5_toi: "Tối Thứ 5",
  T6_sang: "Sáng Thứ 6",
  T6_chieu: "Chiều Thứ 6",
  T6_toi: "Tối Thứ 6",
  T7_sang: "Sáng Thứ 7",
  T7_chieu: "Chiều Thứ 7",
  T7_toi: "Tối Thứ 7",
  CN_sang: "Sáng Chủ nhật",
  CN_chieu: "Chiều Chủ nhật",
  CN_toi: "Tối Chủ nhật",
};

/** `ca_doanh_thu` / `T6_toi` → nhãn tiếng Việt tự nhiên; không nhận diện được
 *  thì chỉ đổi gạch dưới thành khoảng trắng, không in nguyên mã kỹ thuật. */
export function codeLabel(code: unknown): string {
  const raw = safeText(code, "");
  if (!raw) return DASH;
  if (CODE_LABELS[raw]) return CODE_LABELS[raw];
  if (raw.includes("_")) return raw.replace(/_/g, " ");
  return raw;
}

/* ── Vị trí / chức vụ ca ── */

const VI_TRI: Record<string, string> = {
  thu_ngan: "Thu ngân",
  pha_che: "Pha chế",
  phuc_vu: "Phục vụ",
  kho: "Kho",
  quan_ly_ca: "Quản lý ca",
  da_nang: "Đa năng",
};

export function viTriLabel(code: unknown): string {
  const raw = safeText(code, "");
  if (!raw) return "Chưa ghi vị trí";
  return pick(VI_TRI, raw, raw.includes("_") ? raw.replace(/_/g, " ") : raw);
}

/** Ca từ picker API — không in mã nội bộ lên nhãn chính. */
export function caHumanLabel(
  shift?: { label?: string; thu?: string; bat_dau?: string; ket_thuc?: string; vi_tri?: string } | null,
  fallbackId?: string | null,
): string {
  if (shift?.label) return shift.label;
  const thu = safeText(shift?.thu, "");
  const bat = safeText(shift?.bat_dau, "");
  const ket = safeText(shift?.ket_thuc, "");
  const vi = shift?.vi_tri ? viTriLabel(shift.vi_tri) : "";
  const parts = [thu, bat && ket ? `${bat}–${ket}` : "", vi].filter(Boolean);
  if (parts.length) return parts.join(" · ");
  return fallbackId ? "Ca trong tuần" : "Chưa chọn ca";
}


function pick(map: Record<string, string>, code: unknown, fallback: string): string {
  const key = typeof code === "string" ? code : "";
  return map[key] ?? fallback;
}

const INBOX: Record<string, string> = {
  cho_duyet: "Chờ người duyệt",
  duyet: "Đã duyệt",
  tu_choi: "Đã từ chối",
  moi: "Mới vào hộp thư",
};

export function inboxLabel(code: unknown): string {
  return pick(INBOX, code, "Chưa rõ trạng thái");
}

export function inboxTone(code: unknown): "warn" | "ok" | "danger" | "default" {
  if (code === "cho_duyet" || code === "moi") return "warn";
  if (code === "duyet") return "ok";
  if (code === "tu_choi") return "danger";
  return "default";
}

const AGENT: Record<string, string> = {
  ag_msg: "Tin nhắn trong ca",
  ag_handover: "Bàn giao ca",
  ag_rule: "Đề xuất luật",
  ag_waste: "Ghi chú hao phí",
  ag_sop: "Câu hỏi SOP",
  ag_tkb: "Thời khoá biểu nhân viên",
};

export function agentLabel(code: unknown): string {
  return pick(AGENT, code, "Nguồn trong quán");
}

const LUAT: Record<string, string> = {
  de_xuat: "Mới đề xuất",
  qua_vf_rule: "Qua vòng kiểm",
  loai: "Bị loại ở vòng kiểm",
  du_tap_su: "Đủ lượt tập sự",
  cho_chu_quan: "Chờ chủ quán chốt",
  truot_tap_su: "Chưa đủ lượt tập sự",
  tu_choi: "Quản lý từ chối",
  hieu_luc: "Đang hiệu lực",
  tu_tat: "Tự tắt vì ít dùng",
};

export function luatLabel(code: unknown): string {
  return pick(LUAT, code, "Chưa rõ trạng thái");
}

export function luatTone(code: unknown): "warn" | "ok" | "danger" | "default" {
  if (code === "hieu_luc") return "ok";
  if (code === "loai" || code === "tu_choi") return "danger";
  if (code === "de_xuat" || code === "truot_tap_su" || code === "cho_chu_quan") return "warn";
  return "default";
}

/* ── Việc treo ──
   Ba trạng thái từ máy chủ (`xong` · `dang_cho` · `qua_han`) là mã nội bộ, phải
   đi qua bảng nhãn như mọi mã khác. Việc treo quá hạn tô đỏ vì đó là việc quán
   đang nợ chính mình. */

const TREO: Record<string, string> = {
  xong: "Đã xong",
  dang_cho: "Đang chờ làm",
  qua_han: "Quá hạn",
  moi: "Mới ghi",
};

export function treoLabel(code: unknown): string {
  return pick(TREO, code, "Chưa rõ trạng thái");
}

export function treoTone(code: unknown): "warn" | "ok" | "danger" | "default" {
  if (code === "xong") return "ok";
  if (code === "qua_han") return "danger";
  if (code === "dang_cho") return "warn";
  return "default";
}

/** Thứ tự đọc: việc quá hạn trước, việc đang chờ, việc đã xong sau cùng. */
export const TREO_THU_TU: readonly string[] = ["qua_han", "dang_cho", "xong"];

/* ── Loại luật trong cẩm nang ── */

const LOAI_LUAT: Record<string, string> = {
  nhu_cau_ca: "Nhu cầu người cho một ca",
  nguong_ton: "Ngưỡng tồn kho",
  buoc_phieu: "Bước bắt buộc trong phiếu",
  ghep_ky_nang: "Ghép kỹ năng vào ca",
  hao_hut: "Nguyên nhân hao hụt",
  nguyen_nhan_hao_hut: "Nguyên nhân hao hụt",
};

export function loaiLuatLabel(code: unknown): string {
  return pick(LOAI_LUAT, code, "Loại luật khác");
}

/**
 * Lý do vòng kiểm loại một luật, nói bằng tiếng Việt.
 *
 * Máy chủ trả mã như `luat_ve_nguoi` hoặc `truong_khong_ton_tai:['ten_nhan_vien']`.
 * In mã thô lên UI là vi phạm mục Disclosure rules, nên ở đây chỉ đọc phần
 * trước dấu hai chấm rồi trả về câu giải thích; phần trong ngoặc (tên trường
 * kỹ thuật) bị bỏ hẳn.
 */
export function vfRuleLyDo(code: unknown): string {
  const raw = safeText(code, "");
  if (!raw) return "Vòng kiểm không ghi lý do.";
  const head = raw.split(":")[0];
  if (head === "dat") return "Luật này qua được vòng kiểm.";
  if (head === "luat_ve_nguoi") {
    return "Vòng kiểm loại vì luật nói về một người cụ thể. Cẩm nang chỉ nhận luật về việc, không nhận luật về người.";
  }
  if (head === "truong_khong_ton_tai") {
    return "Vòng kiểm loại vì luật dựa vào một thông tin quán không có trong hồ sơ ca. Viết lại điều kiện theo thứ, khung giờ hoặc ngưỡng tồn.";
  }
  if (head === "thieu_bang_chung") {
    return "Vòng kiểm loại vì chưa đủ lần sửa thật làm bằng chứng. Ghi thêm vài lần sửa rồi đề xuất lại.";
  }
  if (head === "trung_luat") {
    return "Vòng kiểm loại vì quán đã có một luật nói cùng một việc.";
  }
  return "Vòng kiểm loại luật này. Nhờ quản lý xem lại cách diễn đạt điều kiện.";
}

/* ── Hao phí ── */

const NGUYEN_NHAN: Record<string, string> = {
  dem_sai_dau_ca: "Đếm sai đầu ca",
  roi_do: "Rơi đổ khi làm",
  quen_tat_may: "Quên tắt máy",
  khach_doi_mon: "Khách đổi món",
  het_han: "Hết hạn dùng",
  "pha sai": "Pha sai phải bỏ",
  pha_sai: "Pha sai phải bỏ",
};

export function nguyenNhanLabel(code: unknown): string {
  return pick(NGUYEN_NHAN, code, "Nguyên nhân khác");
}

/* ── Hao hụt định lượng ──
   Ba bảng dưới đây phục vụ mặt /hao-phi mới. Mã trạng thái của máy chủ
   (`thieu_du_lieu`, `ke_hoach_kiem_ke`...) là nội bộ — theo `docs/design-guidelines.md`
   phải đi qua bảng nhãn, không được in thô lên UI. */

const LOSS_LEVEL: Record<string, string> = {
  dat: "Trong ngưỡng",
  canh_bao: "Cần xem lại",
  nghiem_trong: "Vượt ngưỡng nặng",
  thieu_du_lieu: "Chưa đủ dữ liệu",
};

export function lossLevelLabel(code: unknown): string {
  return pick(LOSS_LEVEL, code, "Chưa rõ mức độ");
}

export function lossLevelTone(code: unknown): "warn" | "ok" | "danger" | "default" {
  if (code === "nghiem_trong") return "danger";
  if (code === "canh_bao") return "warn";
  if (code === "dat") return "ok";
  return "default";
}

const LOSS_BASIS: Record<string, string> = {
  ke_hoach_kiem_ke: "Từ phiếu kiểm kê",
  don_quay_thuc_te: "Từ đơn quầy",
  hon_hop: "Đối chiếu đơn quầy với kiểm kê",
};

export function lossBasisLabel(code: unknown): string {
  return pick(LOSS_BASIS, code, "Chưa rõ nguồn số");
}

/** Đọc phần còn thiếu của một dòng hao hụt thành câu người hiểu. */
export function lossThieuVeLabel(thieuVe: unknown): string {
  if (!Array.isArray(thieuVe) || thieuVe.length === 0) return "";
  const co = (x: string) => thieuVe.includes(x);
  if (co("ly_thuyet") && co("thuc_te")) return "Chưa có đơn quầy và chưa có phiếu kiểm kê";
  if (co("ly_thuyet")) return "Chưa có đơn quầy nên chưa biết lượng theo công thức";
  if (co("thuc_te")) return "Chưa gõ phiếu kiểm kê nên chưa biết lượng đã dùng thật";
  return "Chưa đủ dữ liệu để đối chiếu";
}

/** Bốn trường ngày của máy chủ ghi ở bốn đường khác nhau; lấy trường nào có. */
export function lossNgay(row: { luc?: unknown; created_at?: unknown; ngay?: unknown; at?: unknown }): string {
  return safeText(row.luc ?? row.created_at ?? row.ngay ?? row.at, "");
}

const MAT_HANG: Record<string, string> = {
  sua_tuoi: "Sữa tươi",
  ca_phe_hat: "Cà phê hạt",
  tra: "Trà",
  duong: "Đường",
  ly_nhua: "Ly nhựa",
  ong_hut: "Ống hút",
  banh: "Bánh",
  da: "Đá",
  matcha: "Matcha",
};

/** `sua_tuoi` → "sữa tươi". Tên đã là tiếng Việt thì giữ nguyên. */
export function matHangLabel(code: unknown): string {
  const raw = safeText(code, "");
  if (!raw) return "Mặt hàng chưa ghi tên";
  return MAT_HANG[raw] ?? raw;
}

const THU: Record<string, string> = {
  T2: "Thứ Hai",
  T3: "Thứ Ba",
  T4: "Thứ Tư",
  T5: "Thứ Năm",
  T6: "Thứ Sáu",
  T7: "Thứ Bảy",
  CN: "Chủ nhật",
};

export function thuLabel(code: unknown): string {
  return pick(THU, code, "Chưa rõ thứ");
}

/** Thứ tự tuần để nhóm hiển thị không nhảy theo thứ tự máy chủ trả về. */
export const THU_THU_TU: readonly string[] = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

/* ── Mẫu phiếu ── */

const MAU_PHIEU: Record<string, string> = {
  mo_quan: "Mở quán",
  dong_quan: "Đóng quán",
  ban_giao_ca: "Bàn giao ca",
};

export function mauPhieuLabel(code: unknown): string {
  return pick(MAU_PHIEU, code, "Phiếu ca");
}

/** Phiếu gắn vào lúc nào trong ngày — nói bằng lời, không dùng mã `ca_dau_ngay`. */
const GAN_VOI: Record<string, string> = {
  ca_dau_ngay: "Chạy ở ca đầu ngày, trước khi mở cửa cho khách",
  ca_cuoi_ngay: "Chạy ở ca cuối ngày, trước khi khoá cửa",
  giao_ca: "Chạy lúc giao ca, khi người ca trước rời quầy",
};

export function ganVoiLabel(code: unknown): string {
  return pick(GAN_VOI, code, "Chạy trong ca khi cần");
}

/** Điều kiện mở phiếu. Mã `nhan_vien_da_diem_danh` không được ra UI. */
const MO_KHI: Record<string, string> = {
  nhan_vien_da_diem_danh: "mở được sau khi bạn điểm danh",
  ca_ket_thuc: "mở được khi ca sắp kết thúc",
};

export function moKhiLabel(code: unknown): string {
  return pick(MO_KHI, code, "mở được trong ca");
}

/* ── Đăng ký tài khoản ──
   Máy chủ trả 409 với `detail` là một trong bốn mã. Mã thô không được ra UI:
   mỗi mã đổi thành một câu chỉ đúng ô cần sửa. */

export type ODangKy = "username" | "password" | "display_name" | "chung";

const DANG_KY: Record<string, { o: ODangKy; cau: string }> = {
  ten_khong_hop_le: {
    o: "username",
    cau: "Tên đăng nhập chỉ nhận chữ thường không dấu, số và dấu gạch dưới, dài 3–24 ký tự. Sửa lại ô tên đăng nhập.",
  },
  mat_khau_qua_ngan: {
    o: "password",
    cau: "Mật khẩu ngắn quá. Đặt từ 8 ký tự trở lên rồi gửi lại.",
  },
  ten_da_ton_tai: {
    o: "username",
    cau: "Tên đăng nhập này quán đã có người dùng. Chọn một tên khác, ví dụ thêm số ở cuối.",
  },
  thieu_ten_hien_thi: {
    o: "display_name",
    cau: "Tên hiển thị cần 2–60 ký tự để đồng nghiệp nhận ra bạn trên lịch ca.",
  },
};

/**
 * Đổi `detail` của lỗi 409 thành ô cần sửa + câu tiếng Việt.
 * Mã lạ cũng không lọt ra ngoài: rơi vào nhánh "chung" với câu chung.
 */
export function dangKyLoi(detail: unknown): { o: ODangKy; cau: string } {
  const raw = safeText(detail, "");
  return (
    DANG_KY[raw] ?? {
      o: "chung",
      cau: "Thông tin đăng ký chưa hợp lệ. Kiểm tra lại ba ô rồi gửi lại.",
    }
  );
}

/* ── Trích dẫn nguồn của câu trả lời SOP ──
   Máy chủ trả `phieu:<mã bước>` hoặc `luat:<mã luật>`. Mã là khoá để tra tên
   thật, KHÔNG phải thứ để in: trang /sop tra bảng mẫu phiếu và cẩm nang rồi in
   tên bước / câu luật. Không tra được thì in loại nguồn, vẫn không in mã. */

export type TrichDan = { loai: "phieu" | "luat" | "khac"; ma: string; nguon: string };

/* ── Lỗi 409 cụ thể của lịch tuần (roster/lifecycle) ──
   Máy chủ trả `detail` là mã kỹ thuật. Đổi thành câu tiếng Việt người vận hành hiểu. */

export type Lich409Code =
  | "stale_schedule_run"
  | "authoritative_schedule_run_required"
  | "schedule_has_unresolved_gaps"
  | "invalid_schedule_run"
  | "schedule_has_open_shifts"
  | "illegal:may_sinh->nhap"
  | "illegal:nhap->dang_giai"
  | "illegal:dang_giai->cho_duyet"
  | "illegal:dang_giai->nhap"
  | "illegal:cho_duyet->da_duyet"
  | "illegal:cho_duyet->nhap"
  | "illegal:da_duyet->da_cong_bo"
  | "illegal:da_cong_bo->da_dong"
  | "illegal:da_dong->nhap"
  | "chi_ghim_khi_lich_nhap_hoac_cho_duyet"
  | "mo_lai_phai_co_ly_do"
  | "lich_chua_cong_bo"
  | "open_shift_khong_thuoc_run_gap_hop_le"
  | "chua_xac_nhan_kha_dung_dung_tuan"
  | "nhan_vien_da_duoc_xep_ca"
  | "ca_da_duoc_nhan"
  | "chua_du_mau"
  | "luat_chua_cho_chu_quan"
  | "luat_chua_hieu_luc"
  | "thieu_golden_sop"
  | "qr_da_dung"
  | "swap_da_tu_choi"
  | "ca_khong_trong_phan_cong_cua_nguoi_nhuong"
  | "swap_chua_co_nguoi_nhan"
  | "nguoi_nhuong_khong_trong_ca"
  | "tuan_khong_hop_le"
  | "doi_ca_khong_hop_le"
  | "idempotency_conflict"
  | "action_retry_not_safe"
  | "action_decision_conflict"
  | "action_execution_in_progress"
  | "action_execution_conflict"
  | "stale_rejected"
  | "da_quyet_truoc_do"
  | "qua_cua_so_24h"
  | "mail_delivery_in_progress"
  | "mail_idempotency_conflict"
  | "khong_the_vo_hieu_hoa_chinh_minh"
  | "vo_hieu_hoa_that_bai"
  | "chuyen_khong_hop_le"
  | "don_da_ket_thuc"
  | "SCHEMA_VERSION_MISMATCH"
  | string; // fallback cho mã chưa biết

const LICH_409: Record<string, string> = {
  // Lifecycle / schedule run
  stale_schedule_run:
    "Lịch đã được tính toán lại bởi người khác. Tải lại trang để xem phiên bản mới nhất.",
  authoritative_schedule_run_required:
    "Chưa có lịch đã tính toán (chưa chạy solver). Bấm «Xếp lịch tự động» trước.",
  schedule_has_unresolved_gaps:
    "Vẫn còn ca thiếu nhân chưa xử lý. Điền đủ ca thiếu rồi mới duyệt/công bố.",
  invalid_schedule_run:
    "Trạng thái lịch không hợp lệ để duyệt. Chạy lại solver hoặc kiểm tra ca thiếu.",
  schedule_has_open_shifts:
    "Vẫn còn ca mở (chưa ai nhận). Điền hoặc gán nhân sự trước khi công bố.",

  // Chuyển trạng thái không hợp lệ
  "illegal:may_sinh->nhap":
    "Lịch mới sinh ra, chỉ được chuyển sang «Nháp».",
  "illegal:nhap->dang_giai":
    "Từ nháp chỉ được bấm «Xếp lịch tự động».",
  "illegal:dang_giai->cho_duyet":
    "Solver đang chạy, đợi xong sẽ tự chuyển sang «Chờ duyệt».",
  "illegal:dang_giai->nhap":
    "Solver đang chạy, không thể quay về nháp ngay.",
  "illegal:cho_duyet->da_duyet":
    "Từ chờ duyệt chỉ được «Duyệt lịch» hoặc quay về «Nháp».",
  "illegal:cho_duyet->nhap":
    "Quay về nháp được, nhưng hãy chắc chắn muốn hủy duyệt.",
  "illegal:da_duyet->da_cong_bo":
    "Đã duyệt → công bố cho nhân viên.",
  "illegal:da_cong_bo->da_dong":
    "Đã công bố → đóng tuần.",
  "illegal:da_dong->nhap":
    "Đã đóng → chỉ chủ quán mở lại được (cần lý do).",

  // Pin / ghim
  chi_ghim_khi_lich_nhap_hoac_cho_duyet:
    "Chỉ ghim được khi lịch ở trạng thái «Nháp» hoặc «Chờ duyệt».",

  // Mở lại lịch
  mo_lai_phai_co_ly_do:
    "Mở lại lịch đã đóng cần ghi lý do. Nhập lý do rồi thử lại.",

  // Xuất lịch / quyền nhân viên
  lich_chua_cong_bo:
    "Lịch chưa công bố, nhân viên không tải được. Nhờ quản lý công bố trước.",

  // Resolve gaps / open shifts
  open_shift_khong_thuoc_run_gap_hop_le:
    "Ca thiếu này không thuộc lần chạy lịch hiện tại. Tải lại trang.",
  chua_xac_nhan_kha_dung_dung_tuan:
    "Nhân sự này chưa xác nhận giữ ca tuần này.",
  nhan_vien_da_duoc_xep_ca:
    "Nhân viên đã được xếp ca khác trong tuần này.",
  ca_da_duoc_nhan:
    "Ca này đã có người nhận.",

  // Cam nang / SOP
  chua_du_mau:
    "Chưa đủ mẫu phiếu (golden) để chạy cam nang. Cần ít nhất 1 mẫu hoàn chỉnh.",
  luat_chua_cho_chu_quan:
    "Luật này chưa cho phép chủ quán thực hiện.",
  luat_chua_hieu_luc:
    "Luật chưa có hiệu lực.",
  thieu_golden_sop:
    "Thiếu mẫu phiếu chuẩn (golden SOP) để tham chiếu.",

  // QR / check-in
  qr_da_dung:
    "Mã QR này đã được dùng. Yêu cầu mã mới.",

  // Swap ca
  swap_da_tu_choi:
    "Yêu cầu đổi ca đã bị từ chối.",
  ca_khong_trong_phan_cong_cua_nguoi_nhuong:
    "Người nhường không còn giữ ca này — phiếu hỏng, hãy đóng và mở lại.",
  swap_chua_co_nguoi_nhan:
    "Phiếu mở cho mọi người nhưng chưa ai nhận — chưa duyệt được.",
  nguoi_nhuong_khong_trong_ca:
    "Bạn không giữ ca này trong tuần đã chọn — kiểm tra lại ca và tuần rồi mở lại phiếu.",
  tuan_khong_hop_le:
    "Tuần không hợp lệ (đúng dạng 2026-W40). Chọn lại tuần rồi thử lại.",
  doi_ca_khong_hop_le:
    "Phiếu đổi ca không hợp lệ (tự đổi cho mình hoặc ca không tồn tại).",

  // Copilot / actions
  idempotency_conflict:
    "Yêu cầu trùng lặp (idempotency). Đã xử lý trước đó.",
  action_retry_not_safe:
    "Không thể thử lại hành động này an toàn.",
  action_decision_conflict:
    "Quyết định xung đột (người khác đã quyết định). Tải lại trang.",
  action_execution_in_progress:
    "Hành động đang được thực thi. Đợi xong rồi thử lại.",
  action_execution_conflict:
    "Xung đột khi thực thi hành động. Tải lại trang.",
  stale_rejected:
    "Phiên bản cũ bị từ chối. Tải lại trang để lấy phiên bản mới.",

  // Channels / moderation
  da_quyet_truoc_do:
    "Đã quyết định trước đó. Không thể quyết định lại.",
  qua_cua_so_24h:
    "Quá cửa sổ 24h để xử lý.",

  // Mail
  mail_delivery_in_progress:
    "Đang gửi thư, đợi xong rồi thử lại.",
  mail_idempotency_conflict:
    "Thư này đã được gửi (idempotency).",

  // POS
  khong_the_vo_hieu_hoa_chinh_minh:
    "Không thể vô hiệu hóa chính mình.",
  vo_hieu_hoa_that_bai:
    "Vô hiệu hóa thất bại.",
  chuyen_khong_hop_le:
    "Chuyển trạng thái không hợp lệ.",
  don_da_ket_thuc:
    "Đơn đã kết thúc.",

  // Pricing radar
  SCHEMA_VERSION_MISMATCH:
    "Phiên bản schema khảo sát không khớp. Cập nhật ứng dụng rồi thử lại.",
};

/**
 * Đổi `detail` của lỗi 409 (lịch tuần / lifecycle / solver / cam nang / QR / POS / mail / channels)
 * thành câu tiếng Việt người vận hành hiểu.
 * Mã lạ rơi vào nhánh chung: "Dữ liệu vừa đổi ở nơi khác. Tải lại trang rồi làm lại từ đầu."
 */
export function lich409Loi(detail: unknown): string {
  const raw = safeText(detail, "");
  // Thử khớp chính xác trước
  if (LICH_409[raw]) return LICH_409[raw];
  // Thử khớp prefix cho các mã dạng "illegal:cur->next" hoặc "chuyen_khong_hop_le:..."
  for (const [code, msg] of Object.entries(LICH_409)) {
    if (raw.startsWith(code)) return msg;
  }
  // Fallback chung
  return "Dữ liệu vừa đổi ở nơi khác. Tải lại trang rồi làm lại từ đầu.";
}

/**
 * Mã lỗi OAuth Gmail → câu tiếng Việt + việc cần làm.
 *
 * Vì sao cần bảng riêng: các mã này KHÔNG đi qua `viError()` như lỗi thường —
 * chúng đến từ query string `/gmail?error=...` do API chuyển hướng về, nên
 * không có `ApiError` kèm `status` để `viError()` phân loại. Nếu để rơi vào
 * nhánh 400 chung, người dùng chỉ thấy "Thông tin nhập chưa hợp lệ" — vô nghĩa
 * vì họ chưa nhập gì cả, mà lại không biết phải làm gì tiếp.
 */
const GMAIL_OAUTH_LOI: Record<string, string> = {
  chua_cau_hinh_oauth_gmail:
    "Máy chủ chưa cấu hình Gmail OAuth. Nhờ quản trị điền NHIPQUAN_GMAIL_CLIENT_ID và NHIPQUAN_GMAIL_CLIENT_SECRET vào .env rồi khởi động lại API.",
  thieu_state_oauth: "Phiên kết nối Google thiếu mã xác minh. Bấm Kết nối Gmail rồi làm lại từ đầu.",
  state_oauth_khong_hop_le:
    "Phiên kết nối đã dùng hoặc không hợp lệ. Bấm Kết nối Gmail rồi làm lại từ đầu.",
  state_oauth_het_han: "Phiên kết nối đã quá 10 phút. Bấm Kết nối Gmail rồi làm lại từ đầu.",
  state_oauth_sai_nguoi: "Phiên kết nối này của nhân viên khác. Bấm Kết nối Gmail bằng tài khoản của bạn.",
  thieu_ma_oauth: "Google không trả về mã uỷ quyền. Bấm Kết nối Gmail rồi làm lại từ đầu.",
  doi_ma_oauth_that_bai:
    "Không đổi được mã uỷ quyền với Google. Kiểm tra Redirect URI khai trên Google Cloud Console có khớp NHIPQUAN_GMAIL_REDIRECT_URI không, rồi thử lại.",
  khong_doc_duoc_ho_so_gmail:
    "Đã nhận quyền nhưng không đọc được hồ sơ hộp thư. Kiểm tra Gmail API đã bật trên Google Cloud chưa, rồi thử lại.",
  khong_lay_duoc_email_gmail: "Không lấy được địa chỉ Gmail từ hồ sơ Google. Thử lại; nếu vẫn vậy nhờ quản trị kiểm tra.",
  khong_tim_thay_tai_khoan: "Không tìm thấy nhân viên gắn với phiên kết nối. Bấm Kết nối Gmail rồi làm lại.",
};

/** Đổi `error` trên query string sau OAuth callback thành câu tiếng Việt. */
export function loiOAuthGmail(detail: unknown): string {
  const raw = safeText(detail, "");
  if (!raw) return "Không hoàn tất được kết nối Gmail. Bấm Kết nối Gmail rồi làm lại từ đầu.";
  // Google trả mã chuẩn OAuth (access_denied, invalid_client…) qua tiền tố
  // `google_tu_choi:` do API gắn vào — xem `gmail.py`.
  if (raw.startsWith("google_tu_choi:")) {
    const ma = raw.slice("google_tu_choi:".length);
    if (ma === "access_denied") {
      return "Bạn đã bấm Huỷ ở màn hình đồng ý của Google nên chưa kết nối được. Bấm Kết nối Gmail và chọn Cho phép.";
    }
    return `Google từ chối cấp quyền (${ma}). Kiểm tra Test users và OAuth client trên Google Cloud Console rồi thử lại.`;
  }
  return (
    GMAIL_OAUTH_LOI[raw] ??
    "Không hoàn tất được kết nối Gmail. Bấm Kết nối Gmail rồi làm lại từ đầu."
  );
}

/**
 * Lỗi khi bấm "Kết nối qua Google" nhưng chưa rời khỏi trang.
 *
 * Vì sao cần hàm riêng: `GET /oauth/authorize` trả 503 `chua_cau_hinh_oauth_gmail`
 * khi tiến trình API chưa có Client ID/Secret — đó KHÔNG phải "máy chủ đang lỗi"
 * mà là thiếu cấu hình. Để rơi vào nhánh `status >= 500` của `viError()` thì
 * người dùng nhận "thử lại sau" trong khi thử lại bao nhiêu lần cũng không được.
 * Trả `null` khi không phải case này để caller dùng `viError()` như cũ.
 */
export function loiKetNoiGmail(err: unknown): string | null {
  if (
    err instanceof ApiError &&
    err.status === 503 &&
    err.detail === "chua_cau_hinh_oauth_gmail"
  ) {
    return loiOAuthGmail(err.detail);
  }
  return null;
}

export function trichDanTach(raw: unknown): TrichDan {
  const s = safeText(raw, "");
  const i = s.indexOf(":");
  const dau = i >= 0 ? s.slice(0, i) : "";
  const ma = i >= 0 ? s.slice(i + 1) : "";
  if (dau === "phieu") return { loai: "phieu", ma, nguon: "Mẫu phiếu" };
  if (dau === "luat") return { loai: "luat", ma, nguon: "Cẩm nang" };
  return { loai: "khac", ma: "", nguon: "Nguồn quán" };
}

/** Nhãn người đọc cho trích dẫn SOP (phiếu / luật). */
export function trichDanLabel(
  raw: unknown,
  opts?: { luat?: { id: string; cau?: string }[]; buocTen?: Record<string, string> },
): string {
  const { loai, ma, nguon } = trichDanTach(raw);
  if (!ma) return safeText(raw, nguon);
  if (loai === "luat") {
    const hit = opts?.luat?.find((l) => l.id === ma);
    if (hit?.cau) {
      const c = hit.cau.trim();
      return c.length > 80 ? `${c.slice(0, 80)}…` : c;
    }
    return `Luật ${ma}`;
  }
  if (loai === "phieu") {
    const ten = opts?.buocTen?.[ma];
    if (ten) return ten;
    return ma.replace(/_/g, " ");
  }
  return safeText(raw, nguon);
}

/* ── Ý định tin nhắn trong ca (AG-MSG) ──
   Sáu ý định máy chủ nhận ra từ câu người nhắn. Chip ý định cho người duyệt
   biết đây là loại việc gì trước khi đọc hết tóm tắt. */

const Y_DINH: Record<string, string> = {
  xin_nghi: "Xin nghỉ ca",
  nhan_ca: "Nhận ca",
  doi_ca: "Đổi ca",
  bao_tre: "Báo đến trễ",
  cap_nhat_tkb: "Cập nhật thời khoá biểu",
  khac: "Việc khác trong ca",
};

export function yDinhLabel(code: unknown): string {
  return pick(Y_DINH, code, "Chưa rõ ý định");
}

const KENH: Record<string, string> = {
  zalo: "Zalo",
  telegram: "Telegram",
  facebook: "Facebook",
  console: "Máy chủ",
  quan: "Trong quán",
  page_quan: "Page quán",
};

export function kenhLabel(code: unknown): string {
  return pick(KENH, code, "Kênh khác");
}

/* ── Loại ràng buộc kèm theo một mục hộp thư ── */

const RANG_BUOC: Record<string, string> = {
  khong_xep: "Không xếp vào ca này",
  co_the_xep: "Có thể xếp thêm",
  buoc_them: "Thêm bước vào phiếu",
  nguong_ton: "Ngưỡng tồn kho",
  nhu_cau_ca: "Nhu cầu người cho ca",
  doi_ca: "Đổi ca giữa hai người",
  bao_tre: "Đến trễ, cần bù người",
};

export function rangBuocLabel(code: unknown): string {
  return pick(RANG_BUOC, code, "Ràng buộc khác");
}

const GHI_NHAN: Record<string, string> = {
  pin_ca: "Ghim người vào ca",
  nha_ca: "Nhả ca",
  nhan_ca: "Nhận ca",
  sua_lich: "Sửa lịch tuần",
};

export function ghiNhanLabel(code: unknown): string {
  return pick(GHI_NHAN, code, "Lần sửa trong quán");
}

const HANH_VI: Record<string, string> = {
  lifecycle: "Chuyển trạng thái lịch tuần",
  inbox: "Quyết định hộp thư ràng buộc",
  tieu_thu: "Ghi sổ tiêu thụ",
  cam_nang_8_buoc: "Chạy 8 bước cẩm nang",
  cam_nang_chot: "Chốt luật cẩm nang",
  cam_nang_go: "Gỡ luật khỏi cẩm nang",
  swap: "Mở lệnh đổi ca",
  pin_ca: "Ghim người vào ca",
  "schedule.lifecycle": "Chuyển trạng thái lịch tuần",
  "schedule.lifecycle_reopen": "Mở lại lịch tuần đã đóng",
  "shift_swap.request": "Tạo yêu cầu đổi ca",
  "shift_swap.confirm": "Xác nhận đổi ca",
  "shift_swap.reject": "Từ chối đổi ca",
  "shift_swap.approve": "Duyệt yêu cầu đổi ca",
  "shift_swap.smart_approve": "Trợ lý ảo duyệt đổi ca",
  "constraint.approve": "Duyệt ràng buộc lịch làm việc",
  "constraint.reject": "Từ chối ràng buộc lịch làm việc",
  "inbox_auto_schedule": "Tự động xếp lại lịch tuần",
  "role.promote": "Bổ nhiệm quản lý",
  "role.demote": "Thu hồi quyền quản lý",
  "user.deactivate": "Vô hiệu hóa tài khoản",
  user_deactivate: "Vô hiệu hóa nhân viên",
  "user.login": "Đăng nhập hệ thống",
  "user.login_failed": "Đăng nhập thất bại",
  "user.register": "Tạo tài khoản nhân viên",
  "user.logout": "Đăng xuất hệ thống",
  "attendance.check_in": "Điểm danh vào ca",
  "operation.mutation": "Cập nhật dữ liệu hệ thống",
  "meeting.clarify": "Thảo luận bộ luật",
  "meeting.approve": "Duyệt luật vào cẩm nang",
  "meeting.reject": "Từ chối luật",
  "meeting.rollback": "Rút lại quyết định duyệt luật",
  "meeting.conclude": "Đóng phiên kiểm duyệt",
  "meeting.conclude_empty": "Đóng phiên kiểm duyệt (Trống)",
  "meeting.delete": "Xóa biên bản cuộc họp",
  qr_diem_danh: "Điểm danh vào ca",
  menu_luu: "Lưu món trong thực đơn",
  quay_tao_don: "Tạo đơn tại quầy",
  quay_chuyen_don: "Chuyển trạng thái đơn",
  quay_chinh_don: "Chỉnh sửa đơn",
  kenh_bind: "Liên kết tài khoản kênh",
  page_reply: "Trả lời khách trên trang",
  page_thread_approve: "Duyệt câu trả lời khách",
  fb_inbox_decide: "Xử lý hộp thư Facebook",
  fb_policy_update: "Cập nhật chính sách Facebook",
  cskh_nightly_reflection: "Chạy báo cáo tự đánh giá CSKH",
  apply_cskh_proposal: "Áp dụng đề xuất CSKH",
  store_profile_update: "Cập nhật hồ sơ quán",
  store_promotions_update: "Cập nhật chương trình khuyến mãi",
  page_draft: "Tạo bản nháp nội dung trang",
  queue_review: "Hệ thống chuyển nội dung sang hàng duyệt",
  auto_reply: "Hệ thống tự động trả lời khách",
  block: "Hệ thống chặn nội dung",
};

export function hanhViLabel(code: unknown): string {
  return pick(HANH_VI, code, "Thao tác trong quán");
}

const SWAP: Record<string, string> = {
  cho_xac_nhan: "Chờ đồng ý",
  dong_y: "Đã đủ đồng ý",
  da_duyet: "Đã duyệt",
  tu_choi: "Đã từ chối",
  huy: "Đã hủy",
  // Mã cũ còn sót trong dữ liệu lịch sử — giữ để không hiện "Chưa rõ".
  cho_3_nhanh: "Chờ đồng ý",
};

export function swapLabel(code: unknown): string {
  return pick(SWAP, code, "Chưa rõ trạng thái");
}

const KHUNG: Record<string, string> = {
  sang: "Ca sáng",
  chieu: "Ca chiều",
  toi: "Ca tối",
};

export function khungLabel(code: unknown): string {
  return pick(KHUNG, code, "");
}

/* ── Quầy nội bộ: đơn pha chế và nhóm món ──
   Trạng thái đơn và cách thu tiền là mã nội bộ (`cho_pha`, `da_ck`), không được
   in thẳng ra màn hình quầy — nhân viên đọc "cho pha" không hiểu là gì. Nhóm món
   dùng đúng sáu mã của `data/seed/danh-muc.json` để menu quầy phân mục được. */

const DON_TRANG_THAI: Record<string, string> = {
  cho_pha: "Chờ pha",
  dang_pha: "Đang pha",
  xong: "Đã xong",
  huy: "Đã hủy",
};

export function donTrangThaiLabel(code: unknown): string {
  return pick(DON_TRANG_THAI, code, "Chưa rõ trạng thái");
}

export function donTrangThaiTone(code: unknown): "warn" | "ok" | "danger" | "default" {
  if (code === "xong") return "ok";
  if (code === "huy") return "danger";
  if (code === "dang_pha") return "warn";
  return "default";
}

const DON_THANH_TOAN: Record<string, string> = {
  chua_thu: "Chưa thu",
  tien_mat: "Tiền mặt",
  da_ck: "Đã chuyển khoản",
};

export function donThanhToanLabel(code: unknown): string {
  return pick(DON_THANH_TOAN, code, "Chưa rõ thanh toán");
}

const NHOM_MON: Record<string, string> = {
  ca_phe: "Cà phê",
  tra: "Trà & trà sữa",
  sinh_to: "Sinh tố & đá xay",
  banh: "Bánh & ăn kèm",
  nuoc_dong_chai: "Nước đóng chai",
  nguyen_lieu: "Nguyên liệu pha chế",
};

export function nhomMonLabel(code: unknown): string {
  return pick(NHOM_MON, code, "Món khác");
}

/** Thứ tự đọc menu: đồ uống pha trước, đồ ăn kèm và hàng đóng gói sau cùng. */
export const NHOM_MON_THU_TU: readonly string[] = [
  "ca_phe",
  "tra",
  "sinh_to",
  "banh",
  "nuoc_dong_chai",
  "nguyen_lieu",
];

const LOAI_BUOC: Record<string, string> = {
  photo: "Bước cần ảnh minh chứng",
  text: "Bước cần nhập số liệu",
  nhap: "Bước cần nhập số liệu",
  check: "Bước xác nhận bằng tay",
  doc: "Bước đọc và làm theo",
};

export function loaiBuocLabel(code: unknown): string {
  return pick(LOAI_BUOC, code, "Bước trong phiếu");
}

/* ── Thời gian ── */

/** ISO → "23/08 14:05". Chuỗi rác trả về gạch thay vì "Invalid Date". */
export function formatLuc(value?: string | null): string {
  const raw = safeText(value, "");
  if (!raw) return DASH;
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return DASH;
  const p2 = (n: number) => String(n).padStart(2, "0");
  return `${p2(d.getDate())}/${p2(d.getMonth() + 1)} ${p2(d.getHours())}:${p2(d.getMinutes())}`;
}

/** Ngày ISO `2026-08-23` → "23/08". Không đụng tới chuỗi lạ. */
export function formatNgay(value?: string | null): string {
  const raw = safeText(value, "");
  const m = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}/${m[2]}` : raw || DASH;
}

/**
 * Che mã một lần. Mã điểm danh là bí mật dùng-một-lần: in nguyên lên màn hình
 * là để lộ credential (`docs/design-guidelines.md` — Disclosure rules).
 */
export function maskCode(code: string): string {
  const raw = safeText(code, "");
  if (!raw) return DASH;
  if (raw.length <= 4) return "••••";
  return `•••• •••• ${raw.slice(-4)}`;
}

/* ── Khảo sát giá thị trường (`/khao-sat-gia`) ──
   Mã trạng thái và mã lỗi của plan `260913-1455` mục 2.4/5.3 là nội bộ; UI chỉ
   được nói tiếng Việt kèm hành động kế tiếp (`docs/design-guidelines.md`). */

const KHAO_SAT_TRANG_THAI: Record<string, string> = {
  queued: "Đang xếp hàng",
  scraping_online: "Đang quét kênh giao hàng",
  scraping_dinein: "Đang quét quán tại chỗ",
  ocr_processing: "Đang đọc ảnh thực đơn",
  needs_review: "Chờ bạn xác nhận giá",
  aggregating: "Đang tổng hợp",
  completed: "Hoàn tất",
  failed: "Thất bại",
};

export function khaoSatTrangThaiLabel(code: unknown): string {
  return pick(KHAO_SAT_TRANG_THAI, code, "Đang chạy");
}

const KHAO_SAT_LOI: Record<string, string> = {
  INVALID_RADIUS:
    "Bán kính khảo sát chưa hợp lệ. Bán kính tại chỗ tối đa 3 km, giao hàng tối đa 10 km.",
  SCHEMA_VERSION_MISMATCH:
    "Trang đang dùng phiên bản dữ liệu cũ hơn máy chủ. Tải lại trang rồi khảo sát lại.",
  INSUFFICIENT_MARKET_DATA:
    "Khu vực này chưa đủ quán đạt chuẩn để kết luận về giá. Nới rộng bán kính hoặc hạ ngưỡng đánh giá rồi khảo sát lại.",
  RATE_LIMITED:
    "Đã dùng hết lượt khảo sát trong giờ. Mỗi lượt tốn chi phí thật nên chờ một lát rồi khảo sát lại.",
  SOURCE_BLOCKED:
    "Nguồn dữ liệu đang chặn truy cập tự động. Thử lại sau ít phút; nếu vẫn vậy báo quản lý.",
  VISION_QUOTA_EXCEEDED:
    "Hạn mức đọc ảnh thực đơn tháng này đã hết. Báo quản lý để nạp thêm rồi khảo sát lại.",
  MISSING_IDEMPOTENCY_KEY: "Phiên gửi bị lặp. Bấm khảo sát lại một lần nữa.",
  JOB_NOT_COMPLETED: "Khảo sát chưa chạy xong nên chưa có kết quả.",
  JOB_NOT_NEEDS_REVIEW: "Khảo sát này không còn ở bước chờ xác nhận giá.",
};

/**
 * Mã lỗi khảo sát → câu tiếng Việt + hành động kế tiếp.
 * `fallback` dùng khi máy chủ trả mã chưa có trong bảng — vẫn không in mã thô.
 */
export function khaoSatLoiLabel(code: unknown, fallback?: string): string {
  const key = typeof code === "string" ? code : "";
  return KHAO_SAT_LOI[key] ?? fallback ?? "Khảo sát gặp sự cố. Thử lại sau ít phút.";
}

const DINH_VI: Record<string, string> = {
  street_food: "Bình dân / vỉa hè",
  casual_dine_in: "Quán ngồi thoải mái",
  branded_chain: "Chuỗi thương hiệu",
};

export function dinhViLabel(code: unknown): string {
  return pick(DINH_VI, code, "Chưa xác định phân khúc");
}

const LOAI_KHU_VUC: Record<string, string> = {
  office: "Khu văn phòng",
  residential: "Khu dân cư",
  mixed: "Khu hỗn hợp",
  tourist: "Khu du lịch",
};

/** `area_type` có thể `null` — chưa suy ra được thì nói thẳng là chưa rõ, không bịa. */
export function loaiKhuVucLabel(code: unknown): string {
  return pick(LOAI_KHU_VUC, code, "Chưa rõ loại khu vực");
}

const KENH_GIA: Record<string, string> = {
  delivery_platform: "Kênh giao hàng",
  dine_in_vision: "Tại chỗ (đọc ảnh thực đơn)",
  hybrid: "Cả hai kênh",
};

export function kenhGiaLabel(code: unknown): string {
  return pick(KENH_GIA, code, "Kênh khảo sát");
}

const LY_DO_REVIEW: Record<string, string> = {
  price_unreadable: "Ảnh mờ, không đọc chắc được giá",
  price_outlier: "Giá lệch bất thường so với các quán cùng khu",
  low_confidence: "Máy đọc ảnh chưa đủ tự tin",
  ambiguous_item: "Không rõ tên món thuộc nhóm nào",
};

export function lyDoReviewLabel(code: unknown): string {
  return pick(LY_DO_REVIEW, code, "Cần bạn kiểm tra lại");
}

/** `com_tam` → "cơm tấm". Tên danh mục đã có dấu thì giữ nguyên. */
export function danhMucLabel(code: unknown): string {
  const raw = safeText(code, "");
  if (!raw) return "Danh mục chưa ghi tên";
  return raw.replace(/_/g, " ");
}

const TIEN_VND = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });

/** Giá tiền: `45000` → "45.000đ". Giá trị không phải số → dấu gạch. */
export function giaVnd(value: unknown): string {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? `${TIEN_VND.format(n)}đ` : DASH;
}
