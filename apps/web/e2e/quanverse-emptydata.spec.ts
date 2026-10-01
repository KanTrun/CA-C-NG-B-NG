import { expect, test } from "@playwright/test";
import { disableWebgl, loginAs } from "./_helpers";

/**
 * QUÁNVERSE 2.0 — dữ liệu VẮNG MẶT (S3).
 *
 * Yêu cầu chốt: trống hoàn toàn → KHÔNG gọi JEV, không đoán, không số 0 giả.
 * Hiện card "CHƯA ĐỦ DỮ LIỆU" + checklist 3 nguồn + CTA tới nghiệp vụ thật.
 */

test.describe("QUÁNVERSE 2.0 — không có dữ liệu", () => {
  test.beforeEach(async ({ page }) => {
    await disableWebgl(page);
    await loginAs(page);
  });

  test("API lỗi hết thì hiện S3 chứ KHÔNG hiện 0 giả", async ({ page }) => {
    await page.route("**/api/v1/**", (route) =>
      route.fulfill({ status: 503, contentType: "application/json", body: "{}" }),
    );

    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });

    await expect(page.getByTestId("quanverse-insufficient")).toBeVisible();
    await expect(page.getByTestId("insufficient-headline")).toContainText("CHƯA ĐỦ DỮ LIỆU");
    // Không số 0 giả nào trong card trống.
    await expect(page.getByTestId("quanverse-insufficient")).not.toContainText("0 đơn");
  });

  test("checklist 3 nguồn + CTA tới nghiệp vụ thật", async ({ page }) => {
    await page.route("**/api/v1/**", (route) =>
      route.fulfill({ status: 503, contentType: "application/json", body: "{}" }),
    );

    await page.goto("/quanverse");
    await expect(page.getByTestId("insufficient-checklist")).toBeVisible({ timeout: 15_000 });

    const list = await page.getByTestId("insufficient-checklist").innerText();
    expect(list).toContain("Đơn hàng");
    expect(list).toContain("Lịch ca");
    expect(list).toContain("Tồn kho");
    await expect(page.getByRole("link", { name: "Ghi đơn đầu" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Mở Lịch tuần" })).toBeVisible();
  });

  test("S3 không gọi JEV — không verdict, không top3", async ({ page }) => {
    await page.route("**/api/v1/**", (route) =>
      route.fulfill({ status: 503, contentType: "application/json", body: "{}" }),
    );

    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-insufficient")).toBeVisible({ timeout: 15_000 });

    await expect(page.getByTestId("quanverse-verdict")).toHaveCount(0);
    await expect(page.getByTestId("verdict-headline")).toHaveCount(0);
  });

  test("evidence trống 1 phần vẫn vẽ được nhưng khai thiếu (S2)", async ({ page }) => {
    await page.route("**/api/v1/**", (route) =>
      route.fulfill({ status: 503, contentType: "application/json", body: "{}" }),
    );
    await page.route("**/api/v1/experience/quanverse/evidence**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          trang_thai: "thieu_1_phan",
          coverage: { don: "ok", lich: "ok", kho: "thieu" },
          state: {
            don_dang_xu_ly: 7,
            tong_don: 12,
            quay_pha_tai: 4,
            quay_pha_muc: 5,
            quay_pha_canh_bao: "chu_y",
            nhan_vien_truc: 2,
            ca_hien_tai: "08:00–12:00",
            ton_duoi_nguong: [],
            viec_treo_mo: 0,
            so_ngay_du_lieu: 12,
            gio_dinh: [10],
            tuan_iso: "2026-W40",
          },
          candidates: [
            { id: "A", label: "Mở Lịch tuần", href: "/lich-tuan", source: "Lịch tuần", eligible: false, reason: "Lịch đã đủ." },
            { id: "E", label: "Không làm gì", href: null, source: "Hệ thống", eligible: true, reason: "Giữ nguyên." },
          ],
          nguon: "database_that",
        }),
      }),
    );
    await page.route("**/api/v1/experience/quanverse/jev-judge**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          evidence: {
            trang_thai: "thieu_1_phan",
            coverage: { don: "ok", lich: "ok", kho: "thieu" },
            state: { don_dang_xu_ly: 7 },
            candidates: [],
          },
          jev: {
            goi_jev: true,
            verdict: "theo_doi",
            verdict_label: "Cần theo dõi",
            p: 0.64,
            provider: "fallback",
            latency_ms: 2,
            ranking: [{ id: "E", p: 1 }],
            thieu: ["kho"],
          },
        }),
      }),
    );

    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-verdict")).toBeVisible({ timeout: 15_000 });
    // Phải khai đúng phần thiếu, cấm nhắc số kho.
    await expect(page.getByTestId("verdict-missing")).toContainText("Tồn kho");
  });
});
