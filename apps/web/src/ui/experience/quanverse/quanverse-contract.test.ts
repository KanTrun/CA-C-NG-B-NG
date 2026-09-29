import { describe, expect, it } from "vitest";
import {
  CHUA_CO_DU_LIEU,
  KHONG_CO_DU_LIEU,
  formatSo,
  mangHoacRong,
  mangTho,
  soHoacNull,
} from "./quanverse-contract";

/**
 * Hợp đồng Quánverse — quy ước SỐ.
 *
 * Đây là bài chống hồi quy quan trọng nhất của cả thư mục: bản UI cũ biến dữ
 * liệu vắng mặt thành "0" (`snap.zones?.length ?? 0`), khiến người đọc tưởng
 * quán rảnh trong khi thực ra chưa tải được dữ liệu. Quy ước:
 *
 *   null  = CHƯA CÓ DỮ LIỆU  → "—"
 *   0     = CÓ dữ liệu, bằng không → "0"
 */

describe("formatSo — không bao giờ biến vắng mặt thành 0", () => {
  it("null / undefined / '' / NaN ⇒ gạch, KHÔNG phải 0", () => {
    for (const v of [null, undefined, "", Number.NaN, "abc", Infinity, -Infinity, {}]) {
      const out = formatSo(v as never);
      expect(out, `formatSo(${JSON.stringify(v)})`).toBe(KHONG_CO_DU_LIEU);
      expect(out).not.toBe("0");
    }
  });

  it("số 0 THẬT thì vẫn in 0", () => {
    expect(formatSo(0)).toBe("0");
  });

  it("chuỗi số hợp lệ được đọc như số", () => {
    expect(formatSo("7")).toBe("7");
    expect(formatSo("7.5", { decimals: 1 })).toBe("7.5");
  });

  it("giữ đơn vị khi có", () => {
    expect(formatSo(6, { unit: "nhân sự" })).toBe("6 nhân sự");
    // Không có dữ liệu thì KHÔNG kèm đơn vị — "— nhân sự" gây hiểu nhầm.
    expect(formatSo(null, { unit: "nhân sự" })).toBe(KHONG_CO_DU_LIEU);
  });

  it("làm tròn theo `decimals`", () => {
    expect(formatSo(3.14159, { decimals: 2 })).toBe("3.14");
    expect(formatSo(3, { decimals: 1 })).toBe("3.0");
  });
});

describe("soHoacNull — chuẩn hoá giá trị thô", () => {
  it("giữ số hợp lệ, kể cả 0", () => {
    expect(soHoacNull(0)).toBe(0);
    expect(soHoacNull(7)).toBe(7);
    expect(soHoacNull(-1.5)).toBe(-1.5);
    expect(soHoacNull("42")).toBe(42);
  });

  it("vắng mặt / rác ⇒ null, KHÔNG ⇒ 0", () => {
    for (const v of [null, undefined, "", "  ", "abc", Number.NaN, Infinity, {}, []]) {
      expect(soHoacNull(v), `soHoacNull(${JSON.stringify(v)})`).toBeNull();
    }
  });
});

describe("mangHoacRong / mangTho", () => {
  it("mảng thật thì sao chép, không trả cùng tham chiếu", () => {
    const src = [1, 2, 3];
    const out = mangHoacRong(src);
    expect(out).toEqual(src);
    expect(out).not.toBe(src);
  });

  it("không phải mảng ⇒ rỗng, không ném", () => {
    for (const v of [null, undefined, 0, "", {}, "abc"]) {
      expect(mangHoacRong(v as never)).toEqual([]);
      expect(mangTho(v)).toEqual([]);
    }
  });

  it("mangTho nhận unknown và trả mảng unknown", () => {
    expect(mangTho([1, "a", null])).toHaveLength(3);
  });
});

describe("nhãn hằng số", () => {
  it("gạch và câu 'chưa có dữ liệu' khác nhau về mục đích", () => {
    expect(KHONG_CO_DU_LIEU).toBe("—");
    expect(CHUA_CO_DU_LIEU).toBe("Chưa có dữ liệu");
    expect(KHONG_CO_DU_LIEU).not.toBe(CHUA_CO_DU_LIEU);
  });
});
