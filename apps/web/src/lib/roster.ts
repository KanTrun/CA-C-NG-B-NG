import { khungLabel } from "./present";

export type KhungGio = Record<string, { bat_dau: string; ket_thuc: string }>;

export type RosterShift = {
  id: string;
  thu?: string;
  khung?: string;
  bat_dau?: string;
  ket_thuc?: string;
  vi_tri?: string;
  so_nguoi_toi_thieu?: number;
};

const KHUNG_ORDER = ["sang", "chieu", "toi"] as const;

export function khungOrder(khung: string): number {
  const i = KHUNG_ORDER.indexOf(khung as (typeof KHUNG_ORDER)[number]);
  return i >= 0 ? i : 9;
}

/** Nhãn hàng: "Ca sáng · 06:00 – 11:00" từ data thật, không hardcode. */
export function shiftRowLabel(shift: RosterShift | undefined, khung: string, template?: KhungGio): string {
  const { title, time } = shiftRowParts(shift, khung, template);
  return time ? `${title} · ${time}` : title;
}

/** Tách tiêu đề ca / khung giờ để lưới render hai dòng (đậm + muted). */
export function shiftRowParts(
  shift: RosterShift | undefined,
  khung: string,
  template?: KhungGio,
): { title: string; time: string } {
  const title = khungLabel(khung) || khung;
  const bat = shift?.bat_dau ?? template?.[khung]?.bat_dau;
  const ket = shift?.ket_thuc ?? template?.[khung]?.ket_thuc;
  return { title, time: bat && ket ? `${bat} – ${ket}` : "" };
}

export function shiftTimeRange(shift: RosterShift, template?: KhungGio): string {
  const khung = shift.khung ?? "";
  const bat = shift.bat_dau ?? template?.[khung]?.bat_dau;
  const ket = shift.ket_thuc ?? template?.[khung]?.ket_thuc;
  if (bat && ket) return `${bat} – ${ket}`;
  return "";
}

/** Chữ cái đầu có nghĩa (bỏ "(", số thuần, dấu câu). */
function leadingLetter(word: string): string {
  const m = word.match(/\p{L}/u);
  return m?.[0] ?? "";
}

/**
 * Chữ viết tắt 2 ký tự (tooltip / avatar nhỏ).
 * Tên tiếng Việt 2–4 từ: chữ đầu của từ đầu + chữ đầu của từ cuối chữ cái
 * ("Nguyễn Thị Lan" → "NL"). Tên một từ ("Hân") → hai ký tự chữ cái đầu.
 */
export function initialsOf(name: string): string {
  const core = name.replace(/\s*[（(][^）)]*[）)]\s*/g, " ").trim();
  const words = core.split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  const first = leadingLetter(words[0] ?? "");
  if (words.length === 1) {
    const letters = (words[0] ?? "").match(/\p{L}/gu) ?? [];
    return (letters.slice(0, 2).join("") || first || "?").toUpperCase();
  }
  let last = "";
  for (let i = words.length - 1; i >= 1; i--) {
    last = leadingLetter(words[i] ?? "");
    if (last) break;
  }
  return ((first + last) || "?").toUpperCase();
}

export type ShortNameParts = { primary: string; role?: string };

/**
 * Tách tên ngắn + vai trò cho lưới ca (roster scan).
 *
 * Lỗi cũ: "Nam (pha chế)" bị split theo space rồi lấy chữ đầu của "(pha" → "("
 * → hiện "Nam (." khi CSS ellipsis cắt giữa ngoặc.
 *
 * Quy tắc primary:
 * - Có hậu tố vai trò trong ngoặc → tên gọi (từ cuối), role tách riêng
 * - Một từ → giữ nguyên
 * - Nhiều từ → từ đầu + chữ cái đầu từ cuối có nghĩa ("Uyên B.")
 */
export function shortNameParts(name: string): ShortNameParts {
  const trimmed = name.trim();
  if (!trimmed) return { primary: "?" };

  // Không bao giờ hiển thị MÃ NHÂN SỰ thô (`nv_01`, `nv_26`…) cho người dùng.
  // Mã chỉ lọt tới đây khi một id không tra được tên — dữ liệu có tham chiếu
  // chết. Tầng API đã lọc bỏ (xem `_loc_phan_cong_theo_nhan_su`), nhưng đây là
  // chốt thứ hai: thà hiện "?" còn hơn để người xếp lịch tưởng `nv_26` là tên.
  if (/^nv_\w+$/i.test(trimmed)) return { primary: "?" };

  const roleMatch = trimmed.match(/^(.*?)\s*[（(]([^）)]+)[）)]\s*$/u);
  const core = (roleMatch?.[1] ?? trimmed).trim();
  const role = (roleMatch?.[2] ?? "").trim() || undefined;
  const words = core.split(/\s+/).filter(Boolean);

  if (words.length === 0) return { primary: role ? `(${role})` : "?", role: undefined };

  if (role) {
    return { primary: words[words.length - 1] ?? words[0], role };
  }

  if (words.length === 1) return { primary: words[0] };

  const first = words[0];
  let lastInitial = "";
  for (let i = words.length - 1; i >= 1; i--) {
    lastInitial = leadingLetter(words[i] ?? "").toUpperCase();
    if (lastInitial) break;
  }
  return { primary: lastInitial ? `${first} ${lastInitial}.` : first };
}

/** Tên một dòng (tooltip / nơi không tách role). */
export function shortNameOf(name: string): string {
  const { primary, role } = shortNameParts(name);
  return role ? `${primary} · ${role}` : primary;
}

export function rosterCellSummary(count: number, viTriLabel: string, understaffed?: boolean): {
  countLabel: string;
  roleLabel: string;
  tone: "ok" | "warn" | "empty";
} {
  if (count === 0) {
    // Ô chưa xếp ai là lỗi vận hành, không phải "0 người" trung tính: ca trống
    // nghĩa là quán mở cửa mà không có ai. Tông `empty` tách khỏi `warn` để
    // "thiếu 1 người" và "trống ca" không đọc ra như nhau.
    return { countLabel: "Trống ca", roleLabel: viTriLabel, tone: "empty" };
  }
  return {
    countLabel: `${count} người`,
    roleLabel: viTriLabel,
    tone: understaffed ? "warn" : "ok",
  };
}
