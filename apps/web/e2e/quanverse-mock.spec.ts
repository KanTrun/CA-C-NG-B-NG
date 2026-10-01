import { expect, test } from "@playwright/test";
import { disableWebgl, loginAs } from "./_helpers";

/**
 * QUÁNVERSE 2.0 — KHÔNG còn chế độ mô phỏng riêng.
 *
 * Quyết định chốt: xóa mock. Chỉ dữ liệu thật. Trống thì S3 + Demo Setup qua
 * schema nghiệp vụ thật. Bài này khóa lại: không toggle, không scenario, không
 * badge mô phỏng nào được render.
 */

test.describe("QUÁNVERSE — không còn mô phỏng", () => {
  test.beforeEach(async ({ page }) => {
    await disableWebgl(page);
    await loginAs(page);
  });

  test("không có bộ chọn nguồn mock", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });

    await expect(page.getByTestId("toggle-source")).toHaveCount(0);
    await expect(page.getByTestId("source-scenario")).toHaveCount(0);
    await expect(page.getByTestId("scenario-cao_diem")).toHaveCount(0);
    await expect(page.getByTestId("scenario-binh_thuong")).toHaveCount(0);
    await expect(page.getByTestId("scenario-qua_tai_pha")).toHaveCount(0);
  });

  test("không có badge mô phỏng nào", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });

    await expect(page.getByTestId("timeline-mock-badge")).toHaveCount(0);
    await expect(page.getByText("Dữ liệu mô phỏng")).toHaveCount(0);
  });

  test("nhãn luôn là dữ liệu thật", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("source-badge")).toContainText("Dữ liệu thật", {
      timeout: 15_000,
    });
  });
});
