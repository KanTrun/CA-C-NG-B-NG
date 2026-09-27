import { lifeLabel } from "./session";

/** Nhãn human-facing — không dump mã nội bộ lên hero. */
export function lifeLabelPublic(state: string): string {
  const map: Record<string, string> = {
    may_sinh: "Lịch tự sinh — chờ quản lý rà soát",
    nhap: "Lịch nháp",
    dang_giai: "Đang xếp lịch",
    cho_duyet: "Chờ duyệt",
    da_duyet: "Đã duyệt",
    da_cong_bo: "Lịch đã công bố",
    da_dong: "Tuần đã đóng",
  };
  return map[state] ?? lifeLabel(state);
}

export function todayHeroLine(treo: number, lifeState?: string): string {
  const life = lifeLabelPublic(lifeState ?? "");
  return `${life} · ${treo} việc treo`;
}

/**
 * Dòng phụ của dải "Hôm nay": ngày + số ca, **chỉ những số KHÔNG trùng thẻ KPI**.
 *
 * Vì sao chỉ giữ `so_ca`: bản trước in cả câu brief sáng ở một dòng riêng giữa
 * trang — "Brief sáng {ngày}: {so_ca} ca · {so_treo_mo} việc treo đang mở · tồn
 * cảnh báo: …". Hai trong bốn số đó là số của thẻ KPI ngay bên dưới
 * (`so_treo_mo` = thẻ "Việc treo", `ton_canh_bao` = thẻ "Cảnh báo tồn"), nên màn
 * hình nói cùng một chuyện hai lần ở hai chỗ cách nhau vài chục pixel. `treo_dau`
 * thì trùng khối "Việc treo gần nhất". Chỉ `so_ca` là thông tin chỉ có ở đây.
 *
 * `ngay` truyền vào là ngày ISO của máy chủ (`/api/v1/hom-nay`), KHÔNG phải ngày
 * của brief: brief được worker ghi lúc 06:00 và giữ nguyên cả ngày, nên lấy ngày
 * từ brief sẽ hiện sai ngày nếu worker chưa chạy hôm nay.
 */
export function todayMetaLine(ngay: string, soCa?: number | null): string {
  const parts: string[] = [];
  const d = (ngay || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (d) parts.push(`Ngày ${d[3]}/${d[2]}`);
  if (typeof soCa === "number" && Number.isFinite(soCa) && soCa > 0) {
    parts.push(`${soCa} ca hôm nay`);
  }
  return parts.join(" · ");
}

export function todayTechnicalDetail(lich: {
  trang_thai?: string;
  solver?: { status?: string };
}): string[] {
  const lines: string[] = [];
  if (lich.trang_thai) lines.push(`Trạng thái lịch: ${lifeLabel(lich.trang_thai)}`);
  if (lich.solver?.status) lines.push(`Solver: ${lich.solver.status}`);
  return lines;
}
