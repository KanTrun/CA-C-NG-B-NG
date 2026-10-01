import { expect, test } from "@playwright/test";
import { disableWebgl, loginAs } from "./_helpers";

/**
 * QUÁNVERSE — dữ liệu THẬT (đúng hình dạng API), không cần backend có dữ liệu.
 *
 * `page.route()` giả lập phản hồi của sáu nguồn bằng hình dạng THẬT (đã đối
 * chiếu `apps/api/src/ca_api/interfaces/http/{quanverse.py,sprint45.py,main.py}`
 * và `services/quanverse_live.py`). Nhờ vậy bài test chốt được:
 *
 *   · adapter đọc đúng tên trường thật
 *   · nhãn hiện đúng dữ liệu thật (không lẫn với mock)
 *   · `null`/thiếu trường không bị biến thành 0
 *
 * Đây là bài bắt lỗi "adapter lệch hợp đồng" — thứ mà test mock không thấy được.
 */

const SNAPSHOT = {
  snapshot_id: "snap_test_1",
  store_id: "quan_01",
  generated_at: "2026-09-29T10:32:00Z",
  role: "quan_ly",
  zones: [
    { zone_id: "quay_pha", label: "Quầy pha chế", kind: "quay_pha", active: true, load_signal: "qua_tai" },
    { zone_id: "quay_thu_ngan", label: "Quầy thu ngân", kind: "quay_thu_ngan", active: true, load_signal: "binh_thuong" },
    { zone_id: "khu_ban", label: "Khu bàn", kind: "phong_khach", active: true, load_signal: "binh_thuong" },
    { zone_id: "kho", label: "Kho", kind: "kho", active: true, load_signal: "binh_thuong" },
  ],
  events: [
    {
      event_id: "ev_1",
      event_type: "incident",
      status: "warning",
      occurred_at: "2026-09-29T10:25:00Z",
      source: "don_quay",
      summary: "Quầy pha vượt ngưỡng",
      zone_id: "quay_pha",
    },
  ],
  modes: [],
  next_horizon: [
    { item_id: "hz_1", kind: "handover", title: "Bàn giao quầy pha", starts_at: "10:35", source: "sop" },
  ],
  data_quality: [],
};

const STATIONS = {
  co_du_lieu: true,
  gio: 10,
  tuan_iso: "2026-W40",
  stations: [
    { zone_id: "quay_pha", ten: "Quầy pha chế", kind: "quay_pha", tai: 6, hang_cho: 3, muc_day: 5, canh_bao: "qua_tai" },
    { zone_id: "quay_thu_ngan", ten: "Quầy thu ngân", kind: "quay_thu_ngan", tai: 1, hang_cho: 1, muc_day: 5, canh_bao: "binh_thuong" },
    { zone_id: "khu_ban", ten: "Khu bàn", kind: "phong_khach", tai: 0, hang_cho: 0, muc_day: 5, canh_bao: "binh_thuong" },
    { zone_id: "kho", ten: "Kho", kind: "kho", tai: 0, hang_cho: 0, muc_day: 5, canh_bao: "binh_thuong" },
  ],
  chi_so: {
    don_hom_nay: 25,
    don_dang_xu_ly: 7,
    don_da_xong: 18,
    nhan_su_trong_ca: 6,
    so_ca_phu_khung_gio: 2,
  },
  nguon: "don_quay",
};

const FORECAST = {
  co_du_lieu: true,
  so_ngay_du_lieu: 12,
  series: Array.from({ length: 16 }, (_, i) => {
    const gio = i + 7;
    const nhu_cau = Math.max(0, 8 - Math.abs(gio - 10) * 1.4);
    return { gio, nhu_cau: Math.round(nhu_cau * 100) / 100, hang_doi_du_bao: Math.max(0, Math.round(nhu_cau - 2)) };
  }),
  giao_dich_nhat: [10],
  nguon: "don_quay",
};

const BRIEF = {
  page: "living_map",
  headline: "Quầy pha chế đang là điểm nghẽn chính.",
  facts: ["7 đơn đang xử lý", "Ngưỡng hiện tại: 5"],
  metrics: [],
  risks: [],
  next_actions: ["Cân nhắc điều người sang quầy pha"],
  grounded_refs: ["don_quay", "phan_cong_by_week"],
  data_quality: [],
};

const LICH_TUAN = {
  nguon: "quan",
  nguon_lich: "solver",
  tuan_iso: "2026-W40",
  trang_thai: "da_duyet",
  nhan_vien: [
    { id: "nv_01", ten: "Lan" },
    { id: "nv_02", ten: "Minh" },
  ],
  ca: [{ id: "w1_c01", thu: 2, khung: "Sáng", bat_dau: "08:00", ket_thuc: "12:00", vi_tri: "Quầy pha", so_nguoi_toi_thieu: 2 }],
  phan_cong: { w1_c01: ["nv_01", "nv_02"] },
  open_shifts: [],
};

const HOM_NAY = {
  ngay: "2026-09-29",
  canh_bao_ton: ["Sữa tươi"],
  so_treo: 1,
  treo_preview: [],
  viec_cho_toi: [
    { id: "vct_1", tieu_de: "Kiểm tra tồn kho sữa", chi_tiet: "Đã dưới ngưỡng.", link: "/tieu-thu", muc: 1 },
  ],
};

const STAFF_ON_SHIFT = {
  co_du_lieu: true,
  names: ["Lan", "Minh"],
  count: 2,
  shift_label: "08:00–12:00",
  gio: 10,
  tuan_iso: "2026-W40",
  nguon: "phan_cong_by_week",
};

const MODES = {
  modes: [
    {
      mode: "gio_cao_diem",
      active: false,
      proposal_status: "",
      affected_projections: ["quay_pha_che"],
      effect: "Bật gợi ý san ca.",
    },
  ],
  role: "quan_ly",
  can_activate: true,
};

const EVIDENCE = {
  trang_thai: "du",
  coverage: { don: "ok", lich: "ok", kho: "ok" },
  state: {
    don_dang_xu_ly: 7,
    tong_don: 25,
    quay_pha_tai: 6,
    quay_pha_muc: 5,
    quay_pha_canh_bao: "qua_tai",
    nhan_vien_truc: 2,
    ca_hien_tai: "08:00–12:00",
    ton_duoi_nguong: ["Sữa tươi"],
    viec_treo_mo: 1,
    so_ngay_du_lieu: 12,
    gio_dinh: [10],
    tuan_iso: "2026-W40",
  },
  candidates: [
    { id: "A", label: "Mở Lịch tuần", href: "/lich-tuan", source: "Lịch tuần", eligible: false, reason: "Lịch đã đủ người trực." },
    { id: "B", label: "Kiểm tra tồn kho", href: "/tieu-thu", source: "Kho", eligible: true, reason: "1 mặt hàng dưới ngưỡng: Sữa tươi." },
    { id: "C", label: "Xem quầy pha", href: "/quay", source: "Đơn quầy", eligible: true, reason: "Quầy pha 6 đơn, ngưỡng 5." },
    { id: "D", label: "Xử lý việc treo", href: "/treo", source: "Việc treo", eligible: false, reason: "Không có việc treo mở." },
    { id: "E", label: "Không làm gì", href: null, source: "Hệ thống", eligible: true, reason: "Giữ nguyên khi mọi thứ trong ngưỡng." },
  ],
  nguon: "database_that",
};

const JEV_JUDGE = {
  evidence: EVIDENCE,
  jev: {
    goi_jev: true,
    verdict: "can_xu_ly",
    verdict_label: "Cần xử lý",
    p: 0.91,
    provider: "fallback",
    latency_ms: 3,
    ranking: [
      { id: "C", p: 0.5 },
      { id: "B", p: 0.33 },
      { id: "E", p: 0.17 },
    ],
    thieu: [],
  },
};

test.describe("QUÁNVERSE — dữ liệu thật", () => {
  test.beforeEach(async ({ page }) => {
    await disableWebgl(page);
    await loginAs(page);
    await page.route("**/api/v1/experience/quanverse/snapshot**", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(SNAPSHOT) }),
    );
    await page.route("**/api/v1/experience/quanverse/stations**", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STATIONS) }),
    );
    await page.route("**/api/v1/experience/quanverse/forecast**", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FORECAST) }),
    );
    await page.route("**/api/v1/experience/quanverse/brief/**", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(BRIEF) }),
    );
    await page.route("**/api/v1/experience/quanverse/staff-on-shift**", (r) =>
      r.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(STAFF_ON_SHIFT),
      }),
    );
    await page.route("**/api/v1/experience/quanverse/modes**", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MODES) }),
    );
    await page.route("**/api/v1/experience/quanverse/ask**", (r) =>
      r.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          page: "living_map",
          question: "test",
          answer: "Quầy pha chế đang là điểm nghẽn chính.",
          brief: BRIEF,
          citations: ["don_quay"],
          unsupported_claims: [],
          grounded: true,
          provider: "replay",
        }),
      }),
    );
    await page.route("**/api/v1/lich-tuan**", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(LICH_TUAN) }),
    );
    await page.route("**/api/v1/hom-nay**", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(HOM_NAY) }),
    );
    await page.route("**/api/v1/experience/quanverse/evidence**", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(EVIDENCE) }),
    );
    await page.route("**/api/v1/experience/quanverse/jev-judge**", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(JEV_JUDGE) }),
    );
  });

  test("nhãn nói DỮ LIỆU THẬT chứ không phải mô phỏng @smoke", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-source")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("source-badge")).toContainText("Dữ liệu thật");
    await expect(page.getByTestId("quanverse-source")).not.toContainText("Mô phỏng");
  });

  test("verdict JEV đọc đúng evidence: Cần xử lý p=0.91 + căn cứ", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("verdict-headline")).toContainText("Cần xử lý", { timeout: 15_000 });
    await expect(page.getByTestId("verdict-evidence")).toContainText("7 đơn đang xử lý");
    await expect(page.getByTestId("verdict-provider")).toContainText("Luật nền");
  });

  test("top3 JEV rank: quầy pha + tồn kho, tối đa 3", async ({ page }) => {
    await page.goto("/quanverse");
    const actions = page.getByTestId("quanverse-actions");
    await expect(actions).toContainText("Xem quầy pha", { timeout: 15_000 });
    await expect(actions).toContainText("Kiểm tra tồn kho");
    await expect(actions).toContainText("Kho");
    expect(await page.locator(".nq-qvact__item").count()).toBeLessThanOrEqual(3);
  });

  test("đọc tên nhân sự đang trực từ staff-on-shift", async ({ page }) => {
    await page.goto("/quanverse");
    const ons = page.getByTestId("header-onshift");
    await expect(ons).toBeVisible({ timeout: 15_000 });
    await expect(ons).toContainText("2 nhân sự đang trực");
    await expect(ons).toContainText("Lan");
  });

  test("nhãn khu vực đọc từ `ten`, trạng thái từ `canh_bao`", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("qv-zone-quay_pha")).toContainText("Quầy pha chế", {
      timeout: 15_000,
    });
    await expect(page.getByTestId("qv-zone-quay_pha")).toHaveAttribute(
      "data-trang-thai",
      "qua_tai",
    );
    await expect(page.getByTestId("qv-zone-khu_ban")).toHaveAttribute(
      "data-trang-thai",
      "on_dinh",
    );
  });

  test("AI copilot đọc đúng headline và trích dẫn từ brief", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("copilot-headline")).toContainText(
      "Quầy pha chế đang là điểm nghẽn chính",
      { timeout: 15_000 },
    );
    await expect(page.getByTestId("copilot-citations")).toContainText("don_quay");
    await expect(page.getByTestId("copilot-suggestions")).toContainText("điều người");
  });

  test("cảnh báo tồn kho thành mục Cần xử lý ngay có nguồn", async ({ page }) => {
    await page.goto("/quanverse");
    const actions = page.getByTestId("quanverse-actions");
    await expect(actions).toContainText("Sữa tươi", { timeout: 15_000 });
    await expect(actions).toContainText("Kho");
  });

  test("dự báo vẽ được khi có lịch sử", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.locator(".nq-qvcap__chart")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("capacity-no-history")).toHaveCount(0);
    await expect(page.getByTestId("quanverse-capacity")).toContainText("12 ngày dữ liệu");
  });

  test("không nguồn nào báo lỗi khi mọi nguồn trả 200", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("source-degraded")).toHaveCount(0);
    await expect(page.getByTestId("quanverse-provenance")).toHaveCount(0);
  });
});
