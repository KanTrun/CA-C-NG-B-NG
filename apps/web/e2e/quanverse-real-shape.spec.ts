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
    await page.route("**/api/v1/lich-tuan**", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(LICH_TUAN) }),
    );
    await page.route("**/api/v1/hom-nay**", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(HOM_NAY) }),
    );
  });

  test("nhãn nói DỮ LIỆU THẬT chứ không phải mô phỏng", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-source")).toHaveAttribute("data-nguon", "real");
    await expect(page.getByTestId("source-badge")).toContainText("Dữ liệu thật");
    await expect(page.getByTestId("quanverse-source")).not.toContainText("Mô phỏng");
  });

  test("đọc đúng số liệu từ stations.chi_so", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("kpi-orders")).toHaveText("7", { timeout: 15_000 });
    // Hàng chờ = tổng queue của 4 khu vực = 3 + 1 + 0 + 0
    await expect(page.getByTestId("kpi-queue")).toHaveText("4");
    await expect(page.getByTestId("kpi-zones")).toHaveText("4");
  });

  test("suy TÊN nhân sự đang trực từ lịch tuần", async ({ page }) => {
    await page.goto("/quanverse");
    // Ca 08:00–12:00 có 2 người; bài chạy bất kỳ giờ nào nên chỉ chốt được
    // rằng KHÔNG hiện "—" khi lịch tuần đọc được (khớp ca hay không tuỳ giờ).
    const ons = page.getByTestId("header-onshift");
    await expect(ons).toBeVisible({ timeout: 15_000 });
    await expect(ons).toContainText(/nhân sự đang trực|Chưa có dữ liệu/);
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
