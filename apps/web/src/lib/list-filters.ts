/**
 * Bộ lọc danh sách dùng chung — tìm kiếm, trạng thái, người, thời gian.
 */

export type TimeFilter = "all" | "today" | "week" | "month";

export const TIME_FILTER_OPTIONS: { value: TimeFilter; label: string }[] = [
  { value: "all", label: "Mọi thời điểm" },
  { value: "today", label: "Hôm nay" },
  { value: "week", label: "7 ngày qua" },
  { value: "month", label: "30 ngày qua" },
];

/**
 * Bỏ dấu + hạ chữ thường để so khớp tiếng Việt không phân biệt dấu.
 *
 * Phải bỏ riêng `đ`/`Đ` TRƯỚC khi NFD: U+0111 là ký tự có sẵn dấu mũ, NFD không
 * tách nó ra thành `d` + dấu, nên nếu chỉ dựa vào `normalize("NFD")` thì tìm
 * "da" không ra "đá" và tìm "đa" không ra "da". Ô tìm món ở `/quay` và tìm đơn ở
 * `/pha` đều dùng hàm này.
 */
export function normalize(s: string): string {
  return s
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .trim();
}

export function matchSearch(haystack: string, needle: string): boolean {
  const q = normalize(needle);
  if (!q) return true;
  return normalize(haystack).includes(q);
}

export function matchExact(value: string | undefined, filter: string): boolean {
  if (!filter || filter === "all") return true;
  return (value ?? "") === filter;
}

function startOfDay(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

export function matchTime(iso: string | undefined, filter: TimeFilter): boolean {
  if (!filter || filter === "all") return true;
  if (!iso) return false;
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return false;
  const now = new Date();
  const day = startOfDay(now).getTime();
  if (filter === "today") return t >= day;
  if (filter === "week") return t >= day - 7 * 86400000;
  if (filter === "month") return t >= day - 30 * 86400000;
  return true;
}

export function uniqueSorted(values: Array<string | undefined>): string[] {
  return [...new Set(values.filter((v): v is string => !!v && v.trim().length > 0))].sort((a, b) =>
    a.localeCompare(b, "vi"),
  );
}

export function filterSummary(shown: number, total: number, active: boolean): string {
  if (!active) return `${total} mục`;
  if (shown === total) return `${shown} mục (đã lọc)`;
  return `${shown} / ${total} mục`;
}
