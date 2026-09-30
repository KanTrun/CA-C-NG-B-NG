import { describe, expect, it } from "vitest";
import {
  chuanHoaCapacity,
  chuanHoaCopilot,
  chuanHoaDataQuality,
  chuanHoaEvents,
  chuanHoaTimeline,
  chuanHoaZone,
  gioTuPhut,
  nhanLoaiSuKien,
  nhanNguon,
  trangThaiZoneTuCanhBao,
} from "./mappers";

/**
 * Bộ chuẩn hoá — nơi hợp đồng gặp dữ liệu thô của API.
 *
 * Mỗi bài dưới đây chốt một tên trường THẬT mà backend trả, để nếu ai đó đổi
 * hình dạng API thì test đỏ ngay ở đây thay vì lặng lẽ hiện "—" trên màn hình.
 */

describe("chuanHoaZone", () => {
  it("đọc payload /stations (tai/hang_cho/canh_bao)", () => {
    const z = chuanHoaZone({
      zone_id: "quay_pha",
      ten: "Quầy pha chế",
      kind: "quay_pha",
      tai: 6,
      hang_cho: 3,
      muc_day: 5,
      canh_bao: "qua_tai",
    });
    expect(z.zoneId).toBe("quay_pha");
    expect(z.label).toBe("Quầy pha chế");
    expect(z.load).toBe(6);
    expect(z.queue).toBe(3);
    expect(z.threshold).toBe(5);
    expect(z.status).toBe("qua_tai");
    expect(z.alerts).toHaveLength(1);
    expect(z.alerts[0].severity).toBe("danger");
  });

  it("đọc payload /snapshot.zones (label/load_signal) — KHÔNG bịa số tải", () => {
    const z = chuanHoaZone({
      zone_id: "kho",
      label: "Kho",
      kind: "kho",
      active: true,
      load_signal: "binh_thuong",
    });
    expect(z.label).toBe("Kho");
    // Cực kỳ quan trọng: snapshot KHÔNG có số ⇒ null, không phải 0.
    expect(z.load).toBeNull();
    expect(z.queue).toBeNull();
    expect(z.threshold).toBeNull();
    expect(z.status).toBe("on_dinh");
  });

  it("thiếu `canh_bao` lẫn `load_signal` ⇒ chưa có dữ liệu, không phải ổn định", () => {
    const z = chuanHoaZone({ zone_id: "x", ten: "X" });
    expect(z.status).toBe("chua_co_du_lieu");
    expect(z.load).toBeNull();
  });

  it("tải 0 THẬT vẫn là 0 và vẫn ổn định", () => {
    const z = chuanHoaZone({ zone_id: "khu_ban", ten: "Khu bàn", tai: 0, hang_cho: 0, muc_day: 5, canh_bao: "binh_thuong" });
    expect(z.load).toBe(0);
    expect(z.queue).toBe(0);
    expect(z.status).toBe("on_dinh");
  });

  it("`chu_y` sinh cảnh báo mức warn", () => {
    const z = chuanHoaZone({ zone_id: "q", ten: "Q", tai: 4, muc_day: 5, canh_bao: "chu_y" });
    expect(z.status).toBe("chu_y");
    expect(z.alerts[0].severity).toBe("warn");
  });

  it("dùng `label` khi không có `ten` và ngược lại", () => {
    expect(chuanHoaZone({ zone_id: "a", label: "A" }).label).toBe("A");
    expect(chuanHoaZone({ zone_id: "a", ten: "B" }).label).toBe("B");
    // Không có cả hai ⇒ rơi về zone_id, không phải chuỗi rỗng.
    expect(chuanHoaZone({ zone_id: "a" }).label).toBe("a");
  });
});

describe("trangThaiZoneTuCanhBao", () => {
  it("ánh xạ đúng từ vựng của backend", () => {
    expect(trangThaiZoneTuCanhBao("qua_tai")).toBe("qua_tai");
    expect(trangThaiZoneTuCanhBao("chu_y")).toBe("chu_y");
    expect(trangThaiZoneTuCanhBao("binh_thuong")).toBe("on_dinh");
    expect(trangThaiZoneTuCanhBao("la_hoac")).toBe("chua_co_du_lieu");
    expect(trangThaiZoneTuCanhBao(null)).toBe("chua_co_du_lieu");
    expect(trangThaiZoneTuCanhBao(undefined)).toBe("chua_co_du_lieu");
  });
});

describe("chuanHoaTimeline", () => {
  it("giữ `starts_at` dạng HH:MM khi backend đã cho", () => {
    const ds = chuanHoaTimeline(
      [{ item_id: "h1", kind: "handover", title: "Bàn giao", starts_at: "17:35", source: "sop", status: "sap_toi" }],
      17,
    );
    expect(ds[0].at).toBe("17:35");
    expect(ds[0].source).toBe("SOP");
    expect(ds[0].status).toBe("sap_toi");
  });

  it("suy HH:MM từ `starts_in_min` của fixture", () => {
    const ds = chuanHoaTimeline([{ item_id: "h2", starts_in_min: 40 }], 17);
    expect(ds[0].at).toBe("17:40");
  });

  it("thiếu cả hai mốc ⇒ gạch, không bịa giờ", () => {
    const ds = chuanHoaTimeline([{ item_id: "h3", title: "X" }], 17);
    expect(ds[0].at).toBe("—");
  });

  it("item không có id thì sinh id theo vị trí", () => {
    const ds = chuanHoaTimeline([{ title: "A" }, { title: "B" }], 10);
    expect(ds.map((d) => d.id)).toEqual(["tl_0", "tl_1"]);
  });
});

describe("gioTuPhut", () => {
  it("cộng phút và vòng qua ngày", () => {
    expect(gioTuPhut(17, 40)).toBe("17:40");
    expect(gioTuPhut(23, 30)).toBe("23:30");
    expect(gioTuPhut(17, 60)).toBe("18:00");
    // Vòng qua nửa đêm
    expect(gioTuPhut(23, 90)).toBe("00:30");
  });
});

describe("chuanHoaCapacity", () => {
  it("giữ số khi có dữ liệu", () => {
    const c = chuanHoaCapacity(
      [
        { gio: 7, nhu_cau: 1.5, hang_doi_du_bao: 0 },
        { gio: 8, nhu_cau: 4, hang_doi_du_bao: 2 },
      ],
      true,
      12,
      [8],
    );
    expect(c.hasHistory).toBe(true);
    expect(c.points[0].demand).toBe(1.5);
    expect(c.daysOfData).toBe(12);
    expect(c.peaks).toEqual([8]);
  });

  it("KHÔNG có dữ liệu ⇒ demand null hết, hasHistory false — không vẽ đường 0", () => {
    const c = chuanHoaCapacity(
      [
        { gio: 7, nhu_cau: 0, hang_doi_du_bao: 0 },
        { gio: 8, nhu_cau: 0, hang_doi_du_bao: 0 },
      ],
      false,
      null,
      [],
    );
    expect(c.hasHistory).toBe(false);
    expect(c.points.every((p) => p.demand === null)).toBe(true);
    expect(c.points.every((p) => p.backlog === null)).toBe(true);
    expect(c.peaks).toEqual([]);
  });

  it("co_du_lieu=true nhưng mọi điểm đều null ⇒ vẫn hasHistory false", () => {
    const c = chuanHoaCapacity([{ gio: 7 }, { gio: 8 }], true, 3, []);
    expect(c.hasHistory).toBe(false);
  });
});

describe("chuanHoaCopilot", () => {
  it("ghép brief và ask, giữ trích dẫn", () => {
    const c = chuanHoaCopilot(
      { headline: "Điểm nghẽn: quầy pha", facts: ["7 đơn"], risks: ["Sắp vượt ngưỡng"], next_actions: ["Điều người"], grounded_refs: ["don_quay"] },
      null,
      "fallback",
    );
    expect(c?.headline).toBe("Điểm nghẽn: quầy pha");
    expect(c?.reasons).toEqual(["7 đơn", "Sắp vượt ngưỡng"]);
    expect(c?.citations).toEqual(["don_quay"]);
    expect(c?.grounded).toBe(true);
    expect(c?.suggestedActions).toEqual(["Điều người"]);
  });

  it("ưu tiên `answer` của ask làm headline", () => {
    const c = chuanHoaCopilot({ headline: "Brief" }, { answer: "Trả lời", citations: [], provider: "gemini" }, "fb");
    expect(c?.headline).toBe("Trả lời");
    expect(c?.provider).toBe("gemini");
  });

  it("không trích dẫn và grounded=false ⇒ c?.grounded false, citations rỗng", () => {
    const c = chuanHoaCopilot({ headline: "X", grounded_refs: [] }, null, "fb");
    expect(c?.citations).toEqual([]);
    expect(c?.grounded).toBe(false);
  });

  it("không có gì ⇒ null (UI hiện trạng thái trống)", () => {
    expect(chuanHoaCopilot(null, null, "fb")).toBeNull();
  });

  it("lọc bỏ chuỗi rỗng trong facts/risks", () => {
    const c = chuanHoaCopilot({ facts: ["a", "", "  ", "b"] }, null, "fb");
    expect(c?.reasons).toEqual(["a", "b"]);
  });
});

describe("chuanHoaEvents", () => {
  it("tra nhãn khu vực, mặc định 'Toàn quán'", () => {
    const map = new Map([["quay_pha", "Quầy pha chế"]]);
    const ev = chuanHoaEvents(
      [
        { event_id: "e1", event_type: "incident", summary: "A", zone_id: "quay_pha", occurred_at: "2026-09-29T10:00:00Z" },
        { event_id: "e2", event_type: "signal", summary: "B", zone_id: null },
      ],
      map,
    );
    expect(ev[0].zoneLabel).toBe("Quầy pha chế");
    expect(ev[0].typeLabel).toBe("Sự cố");
    expect(ev[1].zoneLabel).toBe("Toàn quán");
    expect(ev[1].zoneId).toBeNull();
  });

  it("suy nhãn thời gian tương đối khi chỉ có minutes_ago", () => {
    const ev = chuanHoaEvents([{ event_id: "e1", minutes_ago: 12 }], new Map());
    expect(ev[0].occurredAt).toBe("12 phút trước");
  });

  it("id lạ theo loại thì trả chính mã, không im lặng", () => {
    expect(nhanLoaiSuKien("loai_moi")).toBe("loai_moi");
    expect(nhanLoaiSuKien(null)).toBe("Sự kiện");
  });
});

describe("nhanNguon", () => {
  it("đổi mã kỹ thuật thành nhãn đọc được", () => {
    expect(nhanNguon("don_quay")).toBe("Đơn quầy");
    expect(nhanNguon("fixture_mock")).toBe("Dữ liệu mô phỏng");
    // Mã lạ đi thẳng qua — không che giấu nguồn gốc.
    expect(nhanNguon("nguon_la")).toBe("nguon_la");
    expect(nhanNguon(null)).toBe("—");
  });
});

describe("chuanHoaDataQuality", () => {
  it("chuẩn hoá level và giữ message", () => {
    const q = chuanHoaDataQuality([
      { code: "fixture_mock", level: "info", message: "Mô phỏng" },
      { code: "x", level: "lạ", message: "Y" },
    ]);
    expect(q[0].level).toBe("info");
    expect(q[1].level).toBe("info");
    expect(q[1].message).toBe("Y");
  });

  it("bỏ mục rác hoàn toàn", () => {
    expect(chuanHoaDataQuality([{}, null, "x"])).toEqual([]);
    expect(chuanHoaDataQuality(null)).toEqual([]);
  });
});
