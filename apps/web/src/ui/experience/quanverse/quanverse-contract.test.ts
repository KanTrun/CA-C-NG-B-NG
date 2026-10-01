import { describe, expect, it } from "vitest";
import {
  CHUA_CO_DU_LIEU,
  KHONG_CO_DU_LIEU,
  chuanHoaEvidence,
  chuanHoaJev,
  formatSo,
  locActionsTheoZone,
  locEventsTheoZone,
  mangHoacRong,
  mangTho,
  soHoacNull,
  zoneIdTuAction,
  zoneNongNhat,
  type QuanverseActionItem,
  type QuanverseEvent,
  type QuanverseZone,
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

describe("selection helpers — lọc theo khu vực", () => {
  const actions: QuanverseActionItem[] = [
    {
      id: "zone_quay_pha",
      severity: "danger",
      title: "Pha quá tải",
      reason: "r",
      source: "Đơn",
      at: null,
      ctaLabel: null,
      ctaHref: null,
    },
    {
      id: "ton_sua",
      severity: "warn",
      title: "Sữa thấp",
      reason: "r",
      source: "Kho",
      at: null,
      ctaLabel: "Xem",
      ctaHref: "/tieu-thu",
    },
  ];

  const events: QuanverseEvent[] = [
    {
      id: "e1",
      type: "signal",
      typeLabel: "Tín hiệu",
      status: "confirmed",
      occurredAt: "2026-09-30T10:00:00Z",
      source: "ops",
      sourceLabel: "Vận hành",
      summary: "Pha nóng",
      zoneId: "quay_pha",
      zoneLabel: "Quầy pha",
    },
    {
      id: "e2",
      type: "signal",
      typeLabel: "Tín hiệu",
      status: "confirmed",
      occurredAt: "2026-09-30T10:01:00Z",
      source: "ops",
      sourceLabel: "Vận hành",
      summary: "Toàn quán",
      zoneId: null,
      zoneLabel: "Toàn quán",
    },
  ];

  it("zoneIdTuAction đọc id zone_*", () => {
    expect(zoneIdTuAction(actions[0])).toBe("quay_pha");
    expect(zoneIdTuAction(actions[1])).toBeNull();
  });

  it("locActionsTheoZone giữ mục toàn quán + khớp zone", () => {
    const loc = locActionsTheoZone(actions, "quay_pha");
    expect(loc).toHaveLength(2);
    expect(locActionsTheoZone(actions, "kho")).toHaveLength(1);
    expect(locActionsTheoZone(actions, "kho")[0].id).toBe("ton_sua");
  });

  it("locEventsTheoZone giữ event không gắn zone", () => {
    const loc = locEventsTheoZone(events, "quay_pha");
    expect(loc.map((e) => e.id)).toEqual(["e1", "e2"]);
    expect(locEventsTheoZone(events, "kho").map((e) => e.id)).toEqual(["e2"]);
  });

  it("zoneNongNhat ưu tiên quá tải", () => {
    const zones: QuanverseZone[] = [
      {
        zoneId: "a",
        label: "A",
        kind: "k",
        status: "chu_y",
        load: 4,
        threshold: 5,
        queue: 1,
        assignedStaff: 1,
        assignedNames: [],
        alerts: [],
      },
      {
        zoneId: "b",
        label: "B",
        kind: "k",
        status: "qua_tai",
        load: 7,
        threshold: 5,
        queue: 3,
        assignedStaff: 1,
        assignedNames: [],
        alerts: [],
      },
    ];
    expect(zoneNongNhat(zones)).toBe("b");
  });
});

describe("QUÁNVERSE 2.0 — evidence / JEV chuẩn hoá", () => {
  it("evidence đủ: coverage ok + candidates A–E", () => {
    const ev = chuanHoaEvidence({
      trang_thai: "du",
      coverage: { don: "ok", lich: "ok", kho: "ok" },
      state: { don_dang_xu_ly: 7, ton_duoi_nguong: ["Sữa tươi"], gio_dinh: [10] },
      candidates: [{ id: "A", label: "Mở Lịch tuần", href: "/lich-tuan", source: "Lịch", eligible: true, reason: "r" }],
    });
    expect(ev?.trangThai).toBe("du");
    expect(ev?.state.donDangXuLy).toBe(7);
    expect(ev?.candidates).toHaveLength(1);
  });

  it("evidence rác ⇒ trong, số ⇒ null (không 0 giả)", () => {
    const ev = chuanHoaEvidence({ trang_thai: "x", coverage: {}, state: {}, candidates: "x" });
    expect(ev?.trangThai).toBe("trong");
    expect(ev?.state.donDangXuLy).toBeNull();
    expect(ev?.candidates).toEqual([]);
  });

  it("jev verdict lạ ⇒ null; ranking giữ closed-set", () => {
    expect(chuanHoaJev({ goi_jev: true, verdict: "tu_che", ranking: [{ id: "Z", p: 1 }] })?.verdict).toBeNull();
    const jev = chuanHoaJev({
      goi_jev: true, verdict: "can_xu_ly", verdict_label: "Cần xử lý", p: 0.91,
      provider: "fallback", latency_ms: 3, ranking: [{ id: "C", p: 0.5 }], thieu: ["kho"],
    });
    expect(jev?.verdict).toBe("can_xu_ly");
    expect(jev?.ranking).toEqual([{ id: "C", p: 0.5 }]);
    expect(jev?.thieu).toEqual(["kho"]);
  });

  it("trong ⇒ jev không gọi", () => {
    const jev = chuanHoaJev({ goi_jev: false, verdict: null, p: null, provider: "none", ranking: [] });
    expect(jev?.goiJev).toBe(false);
    expect(jev?.provider).toBe("none");
  });
});
