/**
 * Lọc mail liên quan quán — dùng cho trang /gmail (tab Hộp thư).
 *
 * Vì sao có file riêng: tiêu chí "mail quán" dùng ở nhiều chỗ (bộ lọc nhanh,
 * đếm ẩn/hiện, gợi ý tạo Gmail filter) nên gom một nguồn sự thật thay vì rải
 * keyword trong page.tsx. Không phụ thuộc React để test được bằng vitest.
 */

export type QuanMailInput = {
  from_email?: string | null;
  subject?: string | null;
  snippet?: string | null;
};

export type QuanNhomId = "" | "don_hang" | "nha_cung_cap" | "dat_ban" | "khieu_nai" | "tai_chinh";

export const QUAN_NHOM: { id: QuanNhomId; label: string; goi_y: string }[] = [
  { id: "", label: "Tất cả mail quán", goi_y: "" },
  { id: "don_hang", label: "Đơn hàng / giao đồ ăn", goi_y: "ShopeeFood, GrabFood, đơn hàng, giao hàng" },
  { id: "nha_cung_cap", label: "Nhà cung cấp / nguyên liệu", goi_y: "nhà cung cấp, nguyên liệu, nhập hàng, báo giá" },
  { id: "dat_ban", label: "Đặt bàn / đặt món", goi_y: "đặt bàn, đặt món, reservation, booking" },
  { id: "khieu_nai", label: "Khiếu nại / đánh giá", goi_y: "khiếu nại, phản hồi, đánh giá, review" },
  { id: "tai_chinh", label: "Hoá đơn / công nợ", goi_y: "hoá đơn, công nợ, thanh toán, invoice" },
];

/** Từ khoá theo nhóm (dạng không dấu, viết thường — so sau khi chuẩn hoá). */
const NHOM_KEYWORDS: Record<Exclude<QuanNhomId, "">, string[]> = {
  don_hang: [
    "don hang",
    "dat mon",
    "shopeefood",
    "shopee food",
    "grabfood",
    "grab food",
    "befood",
    "loship",
    "giao hang",
    "giao do an",
    "shipper",
    "ma don",
    "xac nhan don",
  ],
  nha_cung_cap: [
    "nha cung cap",
    "ncc",
    "cung ung",
    "cung cap",
    "nguyen lieu",
    "nhap hang",
    "bao gia",
    "chao gia",
    "ca phe hat",
    "sua tuoi",
    "duong",
    "hop dong cung cap",
  ],
  dat_ban: [
    "dat ban",
    "dat mon",
    "reservation",
    "booking",
    "giu ban",
    "giu cho",
    "khach dat",
    "tiec",
  ],
  khieu_nai: [
    "khieu nai",
    "phan hoi",
    "danh gia",
    "review",
    "rating",
    "gop y",
    "khong hai long",
    "xin loi",
    "google maps",
  ],
  tai_chinh: [
    "hoa don",
    "invoice",
    "cong no",
    "thanh toan",
    "payment",
    "chuyen khoan",
    "sao ke",
    "ngan hang",
    "vietcombank",
    "momo",
    "thue",
    "tien dien",
    "tien nuoc",
    "tien thue",
  ],
};

/** Từ khoá chung của quán (hợp của các nhóm + từ vận hành). */
const QUAN_KEYWORDS_CHUNG: string[] = [
  "nhip quan",
  "quan ca phe",
  "ca phe",
  "tra sua",
  "thuc don",
  "menu",
  "khach hang",
  "lien he",
  "contact",
  "tuyen dung",
  "ung tuyen",
  "nhan su",
  "luong",
  "cham cong",
  "ca lam",
  "doi ca",
  "kiem ke",
  "ton kho",
  "hao phi",
  "ve sinh an toan thuc pham",
  "giay phep",
  "khuyen mai",
  "quang cao",
  "marketing",
  "thue mat bang",
  "hop dong",
  "dien nuoc",
  "wifi",
  "internet",
];

/** Người gửi chắc chắn là mail hệ thống, không phải việc quán. */
const HE_THONG_GUI: string[] = [
  "no-reply@google.com",
  "donotreply",
  "do-not-reply",
  "no_reply",
  "mailer-daemon",
  "postmaster",
];

/**
 * Chuẩn hoá để so không dấu: "ĐƠN HÀNG" → "don hang".
 * `đ/Đ` không nằm trong dải NFD nên thay tay.
 */
export function chuanHoaMail(s: unknown): string {
  return String(s ?? "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d");
}

/** Gộp 3 trường hay đọc thành một chuỗi đã chuẩn hoá để quét từ khoá. */
function gopNoiDung(mail: QuanMailInput): string {
  return chuanHoaMail(
    `${mail.from_email ?? ""} ${mail.subject ?? ""} ${mail.snippet ?? ""}`,
  );
}

function trongNhom(haystack: string, nhom: Exclude<QuanNhomId, "">): boolean {
  return NHOM_KEYWORDS[nhom].some((kw) => haystack.includes(kw));
}

/**
 * Mail có liên quan việc quán không.
 * - `nhom=""`: khớp BẤT KỲ từ khoá quán (chung hoặc theo nhóm).
 * - `nhom` cụ thể: chỉ khớp từ khoá của nhóm đó.
 * - Mail từ địa chỉ hệ thống (Google no-reply…) mà không khớp từ khoá quán
 *   thì luôn là false — đây chính là 4 mail hệ thống đang làm đầy hộp thư mẫu.
 */
export function mailLienQuanQuan(mail: QuanMailInput, nhom: QuanNhomId = ""): boolean {
  const haystack = gopNoiDung(mail);
  if (!haystack.trim()) return false;
  if (nhom !== "") return trongNhom(haystack, nhom);
  const tuNhom = (Object.keys(NHOM_KEYWORDS) as Exclude<QuanNhomId, "">[]).some((k) =>
    trongNhom(haystack, k),
  );
  if (tuNhom) return true;
  const tuChung = QUAN_KEYWORDS_CHUNG.some((kw) => haystack.includes(kw));
  if (tuChung) return true;
  const guiHeThong = HE_THONG_GUI.some((d) => haystack.includes(d));
  if (guiHeThong) return false;
  return false;
}

/** Lọc danh sách + đếm số mail hệ thống đã ẩn (để hiện "đã ẩn X mail"). */
export function locMailQuan<T extends QuanMailInput>(
  messages: T[],
  opts: { chi_quan: boolean; nhom?: QuanNhomId },
): { hien: T[]; an: number } {
  if (!opts.chi_quan) return { hien: messages, an: 0 };
  const nhom = opts.nhom ?? "";
  const hien = messages.filter((m) => mailLienQuanQuan(m, nhom));
  return { hien, an: messages.length - hien.length };
}
