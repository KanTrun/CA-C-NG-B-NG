/**
 * Bảng nguyên liệu chuẩn — MIRROR của `data/seed/danh-muc.json` (mảng
 * `nguyen_lieu`).
 *
 * Đây là NGUỒN DUY NHẤT ở web: `ui/bom-editor.tsx` (chọn nguyên liệu khi sửa
 * công thức) và `lib/present.ts` (`matHangLabel`) đều đọc từ đây, không còn
 * bảng riêng. Hai file test chốt cho bảng không được lệch:
 * - `lib/nguyen-lieu.test.ts` — so bảng này với JSON thật bằng `fs`;
 * - `apps/api/tests/unit/test_nguyen_lieu.py` — so bảng Python với cùng JSON.
 *
 * Client component đọc được vì đây là hằng số — không `fs`, không fetch.
 */

export type NguyenLieu = {
  readonly ma: string;
  readonly ten: string;
  readonly don_vi: string;
  readonly nhom: string;
};

/** Thứ tự giữ nguyên như `danh-muc.json` để dropdown không nhảy chỗ. */
export const NGUYEN_LIEU: readonly NguyenLieu[] = [
  { ma: "ca_phe_hat", ten: "Cà phê hạt", don_vi: "g", nhom: "ca_phe" },
  { ma: "sua_tuoi", ten: "Sữa tươi", don_vi: "ml", nhom: "ca_phe" },
  { ma: "sua_dac", ten: "Sữa đặc", don_vi: "ml", nhom: "ca_phe" },
  { ma: "kem", ten: "Kem whipped", don_vi: "g", nhom: "ca_phe" },
  { ma: "duong", ten: "Đường", don_vi: "g", nhom: "ca_phe" },
  { ma: "da", ten: "Đá viên", don_vi: "g", nhom: "ca_phe" },
  { ma: "ly", ten: "Ly / cốc dùng một lần", don_vi: "cái", nhom: "ca_phe" },
  { ma: "ong_hut", ten: "Ống hút", don_vi: "cái", nhom: "ca_phe" },
  { ma: "tra", ten: "Trà", don_vi: "g", nhom: "tra" },
  { ma: "matcha", ten: "Matcha", don_vi: "g", nhom: "tra" },
  { ma: "dao", ten: "Đào / topping trái", don_vi: "g", nhom: "tra" },
  { ma: "syrup", ten: "Syrup", don_vi: "ml", nhom: "tra" },
  { ma: "trai_cay", ten: "Trái cây", don_vi: "g", nhom: "sinh_to" },
  { ma: "banh", ten: "Bánh kèm", don_vi: "cái", nhom: "banh" },
  { ma: "nuoc_dong_chai", ten: "Nước đóng chai", don_vi: "chai", nhom: "nuoc_dong_chai" },
  { ma: "nuoc_loc", ten: "Nước lọc", don_vi: "ml", nhom: "ca_phe" },
];

/**
 * Mã cũ vẫn còn trong DB / đơn quầy cũ → mã chuẩn trong danh mục.
 * Không có bảng này thì `cafe_g` và `ca_phe_hat` là hai mặt hàng khác nhau.
 */
export const ALIAS: Readonly<Record<string, string>> = {
  cafe_g: "ca_phe_hat",
  sua_ml: "sua_tuoi",
  dao_lat: "dao",
  ly_nhua: "ly",
};

const THEO_MA: Readonly<Record<string, NguyenLieu>> = Object.freeze(
  Object.fromEntries(NGUYEN_LIEU.map((i) => [i.ma, i])),
);

/** Mã hợp lệ sau khi qua `ALIAS`; mã lạ trả về nguyên gốc. */
export function chuanHoaMa(key: string): string {
  const ma = key.trim();
  return ALIAS[ma] ?? ma;
}

export function laMaChuan(key: string): boolean {
  return Object.prototype.hasOwnProperty.call(THEO_MA, key);
}

/**
 * Tên tiếng Việt có dấu. Mã lạ → bỏ gạch dưới thay vì bịa tiếng Việt
 * ("sua_dac_nha" → "sua dac nha"), đúng cách Python đang làm.
 */
export function tenNguyenLieu(key: string): string {
  const ma = chuanHoaMa(key);
  return THEO_MA[ma]?.ten ?? ma.replace(/_/g, " ");
}

export function donViNguyenLieu(key: string): string {
  return THEO_MA[chuanHoaMa(key)]?.don_vi ?? "đơn vị";
}

export function nhomNguyenLieu(key: string): string {
  return THEO_MA[chuanHoaMa(key)]?.nhom ?? "";
}

/** Dòng chọn trong `<select>` sửa công thức: { key, label, unit }. */
export const BOM_INGREDIENTS: ReadonlyArray<{ key: string; label: string; unit: string }> = NGUYEN_LIEU.map(
  (i) => ({ key: i.ma, label: i.ten, unit: i.don_vi }),
);

/**
 * `ca_phe_hat` → "Cà phê hạt". Mã lạ GIỮ NGUYÊN (không bỏ gạch dưới) vì chỗ
 * gọi là `matHangLabel(code)` — code không có trong bảng thì mã chính nó vẫn
 * là cái đọc được nhất.
 */
export const MAT_HANG: Readonly<Record<string, string>> = Object.freeze({
  ...Object.fromEntries(
    Object.entries(ALIAS)
      .map(([cu, moi]) => [cu, THEO_MA[moi]?.ten] as const)
      .filter((pair): pair is readonly [string, string] => Boolean(pair[1])),
  ),
  ...Object.fromEntries(NGUYEN_LIEU.map((i) => [i.ma, i.ten])),
});
