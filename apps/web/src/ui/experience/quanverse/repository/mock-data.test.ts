import { describe, expect, it } from "vitest";
import { MOCK_FIXTURES, mockHeader, mockKpis, trangThaiTuTai } from "./mock-data";
import { QUANVERSE_SCENARIOS } from "./types";

/**
 * Fixture mô phỏng — TÍNH NHẤT QUÁN NỘI BỘ.
 *
 * Yêu cầu gốc: "Mock data phải hợp lý và có tính nhất quán. Nếu có 8 đơn đang
 * xử lý thì các zone và alert phải phù hợp. Không tạo số rời rạc."
 *
 * Ràng buộc này chỉ áp cho MOCK. Dữ liệu THẬT do máy chủ tính và có thể không
 * thoả (ví dụ đơn không gắn khu vực), nên không kiểm ở adapter thật.
 */

describe("ba kịch bản đều tồn tại và có nhãn", () => {
  it("có đúng ba kịch bản đã khai", () => {
    expect(Object.keys(MOCK_FIXTURES).sort()).toEqual([...QUANVERSE_SCENARIOS].sort());
  });

  it("mỗi kịch bản có nhãn tiếng Việt không rỗng", () => {
    for (const f of Object.values(MOCK_FIXTURES)) {
      expect(f.scenarioLabel.length).toBeGreaterThan(0);
      expect(f.scenarioLabel).not.toBe(f.scenario);
    }
  });
});

describe("nhất quán nội bộ", () => {
  for (const f of Object.values(MOCK_FIXTURES)) {
    describe(`kịch bản ${f.scenario}`, () => {
      it("có ĐÚNG 4 khu vực, cùng bộ zoneId với backend thật", () => {
        expect(f.zones).toHaveLength(4);
        expect(f.zones.map((z) => z.zoneId).sort()).toEqual(
          ["kho", "khu_ban", "quay_pha", "quay_thu_ngan"].sort(),
        );
      });

      it("tổng tải khu vực == KPI 'Đơn đang xử lý'", () => {
        const kpis = mockKpis(f);
        const don = kpis.find((k) => k.key === "orders")?.value;
        const tongTai = f.zones.reduce((s, z) => s + (z.load ?? 0), 0);
        expect(don).toBe(tongTai);
      });

      it("tổng hàng chờ == KPI 'Đang chờ'", () => {
        const kpis = mockKpis(f);
        const cho = kpis.find((k) => k.key === "queue")?.value;
        const tongCho = f.zones.reduce((s, z) => s + (z.queue ?? 0), 0);
        expect(cho).toBe(tongCho);
      });

      it("số KPI 'Cảnh báo' == số mục cần xử lý", () => {
        const kpis = mockKpis(f);
        const cb = kpis.find((k) => k.key === "alerts")?.value;
        expect(cb).toBe(f.actions.length);
      });

      it("mọi mục khu vực trong `actions` trỏ tới khu vực CÓ THẬT", () => {
        const ids = new Set(f.zones.map((z) => z.zoneId));
        for (const a of f.actions) {
          if (a.id.startsWith("zone_")) {
            expect(ids.has(a.id.slice("zone_".length)), `action lạc: ${a.id}`).toBe(true);
          }
        }
      });

      it("trạng thái khu vực khớp tải (cùng ngưỡng với backend)", () => {
        for (const z of f.zones) {
          expect(z.status).toBe(trangThaiTuTai(z.load));
        }
      });

      it("khu vực quá tải phải có cảnh báo danger", () => {
        for (const z of f.zones.filter((x) => x.status === "qua_tai")) {
          expect(z.alerts.length).toBeGreaterThan(0);
          expect(z.alerts[0].severity).toBe("danger");
        }
      });

      it("`nguon` dữ liệu tự khai là mô phỏng", () => {
        expect(f.dataQuality.some((q) => q.code === "fixture_mock")).toBe(true);
      });

      it("copilot có trích dẫn và đánh dấu grounded", () => {
        expect(f.copilot.citations.length).toBeGreaterThan(0);
        expect(f.copilot.grounded).toBe(true);
      });

      it("timeline và events đều có id duy nhất", () => {
        const tlIds = f.timeline.map((t) => t.id);
        expect(new Set(tlIds).size).toBe(tlIds.length);
        const evIds = f.events.map((e) => e.id);
        expect(new Set(evIds).size).toBe(evIds.length);
      });

      it("event có `zoneId` thì phải nằm trong danh sách khu vực", () => {
        const ids = new Set(f.zones.map((z) => z.zoneId));
        for (const e of f.events) {
          if (e.zoneId !== null) expect(ids.has(e.zoneId), `event lạc: ${e.id}`).toBe(true);
        }
      });

      it("dự báo có 16 điểm 7h→22h", () => {
        expect(f.capacity.points).toHaveLength(16);
        expect(f.capacity.points.map((p) => p.hour)).toEqual(
          Array.from({ length: 16 }, (_, i) => i + 7),
        );
      });

      it("nhu cầu dự báo không âm", () => {
        for (const p of f.capacity.points) {
          expect(p.demand ?? 0).toBeGreaterThanOrEqual(0);
        }
      });

      it("header khớp fixture", () => {
        const h = mockHeader(f);
        expect(h.onShiftCount).toBe(f.nhanSuTrongCa);
        expect(h.shiftLabel).toBe(f.shiftLabel);
      });
    });
  }
});

describe("ba kịch bản KHÁC NHAU thật sự", () => {
  it("tải quầy pha khác nhau giữa các kịch bản", () => {
    const tai = Object.values(MOCK_FIXTURES).map(
      (f) => f.zones.find((z) => z.zoneId === "quay_pha")?.load,
    );
    expect(new Set(tai).size).toBe(tai.length);
  });

  it("chỉ kịch bản quá tải mới có quầy pha vượt ngưỡng", () => {
    expect(MOCK_FIXTURES.qua_tai_pha.zones.find((z) => z.zoneId === "quay_pha")?.status).toBe(
      "qua_tai",
    );
    expect(MOCK_FIXTURES.binh_thuong.zones.find((z) => z.zoneId === "quay_pha")?.status).toBe(
      "on_dinh",
    );
  });

  it("kịch bản 'ca thường' không có việc cần xử lý", () => {
    expect(MOCK_FIXTURES.binh_thuong.actions).toHaveLength(0);
  });
});
