import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  ALIAS,
  BOM_INGREDIENTS,
  MAT_HANG,
  NGUYEN_LIEU,
  chuanHoaMa,
  donViNguyenLieu,
  laMaChuan,
  nhomNguyenLieu,
  tenNguyenLieu,
} from "./nguyen-lieu";

/**
 * `data/seed/danh-muc.json` là nguồn thật (backend đọc nó lúc import). Bảng
 * trong `nguyen-lieu.ts` là mirror bắt buộc phải trùng từng chữ một — nếu lệch
 * thì trang `/menu` mời nhập "Cà phê" mà API lại ghi "Ca phe" là mất dấu.
 *
 * Chốt bằng `ten` viết tay từng mã: so bằng mắt thì `Matcha` không có dấu nên
 * "mọi tên phải có dấu" là điều kiện sai; đúng phải là "đúng chính tả".
 */
const KY_VONG: Record<string, { ten: string; don_vi: string; nhom: string }> = {
  ca_phe_hat: { ten: "Cà phê hạt", don_vi: "g", nhom: "ca_phe" },
  sua_tuoi: { ten: "Sữa tươi", don_vi: "ml", nhom: "ca_phe" },
  sua_dac: { ten: "Sữa đặc", don_vi: "ml", nhom: "ca_phe" },
  kem: { ten: "Kem whipped", don_vi: "g", nhom: "ca_phe" },
  duong: { ten: "Đường", don_vi: "g", nhom: "ca_phe" },
  da: { ten: "Đá viên", don_vi: "g", nhom: "ca_phe" },
  ly: { ten: "Ly / cốc dùng một lần", don_vi: "cái", nhom: "ca_phe" },
  ong_hut: { ten: "Ống hút", don_vi: "cái", nhom: "ca_phe" },
  tra: { ten: "Trà", don_vi: "g", nhom: "tra" },
  matcha: { ten: "Matcha", don_vi: "g", nhom: "tra" },
  dao: { ten: "Đào / topping trái", don_vi: "g", nhom: "tra" },
  syrup: { ten: "Syrup", don_vi: "ml", nhom: "tra" },
  trai_cay: { ten: "Trái cây", don_vi: "g", nhom: "sinh_to" },
  banh: { ten: "Bánh kèm", don_vi: "cái", nhom: "banh" },
  nuoc_dong_chai: { ten: "Nước đóng chai", don_vi: "chai", nhom: "nuoc_dong_chai" },
  nuoc_loc: { ten: "Nước lọc", don_vi: "ml", nhom: "ca_phe" },
};

type Muc = { ma: string; ten: string; don_vi: string; nhom: string };
type Mon = { id?: string; bom?: Record<string, unknown> };
type DanhMuc = { nguyen_lieu: Muc[]; mon?: Mon[] };

/** Không dùng `__dirname` (vitest chạy ESM) và không dùng `process.cwd()`
 * (phụ thuộc nơi gọi lệnh) — anchor vào chính file test. */
const DANH_MUC = fileURLToPath(new URL("../../../../data/seed/danh-muc.json", import.meta.url));

function docDanhMuc(): DanhMuc {
  return JSON.parse(fs.readFileSync(DANH_MUC, "utf8")) as DanhMuc;
}

describe("nguyen-lieu.ts — mirror của data/seed/danh-muc.json", () => {
  it("trùng từng chữ một với bảng JSON", () => {
    expect(NGUYEN_LIEU).toEqual(docDanhMuc().nguyen_lieu);
  });

  it("mọi tên đúng chính tả tiếng Việt", () => {
    expect(Object.keys(KY_VONG).sort()).toEqual(NGUYEN_LIEU.map((i) => i.ma).sort());
    for (const item of NGUYEN_LIEU) {
      expect(item.ten, `tên sai của ${item.ma}`).toBe(KY_VONG[item.ma].ten);
      expect(item.don_vi, `đơn vị sai của ${item.ma}`).toBe(KY_VONG[item.ma].don_vi);
      expect(item.nhom, `nhóm sai của ${item.ma}`).toBe(KY_VONG[item.ma].nhom);
    }
  });

  it("mọi khoá BOM của các món đều tra được (không rớt về 'ca phe hat')", () => {
    for (const mon of docDanhMuc().mon ?? []) {
      for (const ma of Object.keys(mon.bom ?? {})) {
        expect(laMaChuan(ma), `khoá BOM "${ma}" của món ${mon.id} không có trong bảng`).toBe(true);
        expect(tenNguyenLieu(ma), `mất dấu ở ${ma}`).not.toBe(ma.replace(/_/g, " "));
      }
    }
  });

  it("mã alias trỏ vào mã chuẩn có thật", () => {
    for (const [cu, moi] of Object.entries(ALIAS)) {
      expect(laMaChuan(moi), `alias ${cu} → ${moi} không có trong bảng`).toBe(true);
    }
    expect(chuanHoaMa("cafe_g")).toBe("ca_phe_hat");
    expect(chuanHoaMa("Sua tuoi")).toBe("Sua tuoi", "mã lạ giữ nguyên, không đoán");
  });
});

describe("nhãn cho UI", () => {
  it("BOM_INGREDIENTS đủ 16 mã, nhãn và đơn vị lấy từ bảng", () => {
    expect(BOM_INGREDIENTS).toHaveLength(NGUYEN_LIEU.length);
    expect(BOM_INGREDIENTS.map((i) => i.key)).toContain("duong");
    expect(BOM_INGREDIENTS.map((i) => i.key)).toContain("sua_dac");
    expect(BOM_INGREDIENTS.map((i) => i.key)).not.toContain("cafe_g");
    expect(BOM_INGREDIENTS.find((i) => i.key === "ca_phe_hat")).toEqual({
      key: "ca_phe_hat",
      label: "Cà phê hạt",
      unit: "g",
    });
  });

  it("MAT_HANG phủ hết mã trong bảng + mã alias", () => {
    for (const item of NGUYEN_LIEU) expect(MAT_HANG[item.ma]).toBe(item.ten);
    expect(MAT_HANG.cafe_g).toBe("Cà phê hạt");
    expect(MAT_HANG.ly_nhua).toBe("Ly / cốc dùng một lần");
    expect(MAT_HANG.nuoc_dong_chai).toBe("Nước đóng chai");
  });

  it("mã lạ giữ nguyên tên, không bỏ gạch dưới", () => {
    expect(tenNguyenLieu("sua_dac_nha")).toBe("sua dac nha");
    expect(donViNguyenLieu("sua_dac_nha")).toBe("đơn vị");
    expect(nhomNguyenLieu("sua_dac_nha")).toBe("");
    expect(nhomNguyenLieu("tra")).toBe("tra");
  });
});
