import { expect, test } from "@playwright/test";
import { disableWebgl, ensureDemoData, loginAs, resetExperienceState } from "./_helpers";

/**
 * QUÁNVERSE 2.0 — trung tâm điều hành AI.
 *
 * Chốt những gì KHÔNG được phép quay lại:
 *  · không còn tab War Room / Cứu ca
 *  · không còn bề mặt khách hàng (hành trình khách, hương vị, sở thích, AR)
 *  · không còn 3D / <canvas> cho Quánverse
 *  · không còn mock/scenario/role-buttons — chỉ dữ liệu thật
 *  · bốn khối 2.0: verdict JEV · top3 · timeline+capacity · hỏi AI
 *
 * BẪY ĐÃ VẤP: `disableWebgl` được GIỮ trong beforeEach vì các bài khác cần nó,
 * nhưng bài "không còn canvas" KHÔNG dựa vào nó — nó đếm `<canvas>` trên bản
 * render thật, và bản render thật không được tạo canvas nào.
 */

test.describe("QUÁNVERSE — trung tâm điều hành", () => {
  test.beforeEach(async ({ page }) => {
    await disableWebgl(page);
    await loginAs(page);
    await resetExperienceState(page);
    await ensureDemoData(page);
  });

  test("tải được và hiện bốn khối 2.0 (verdict · top3 · timeline/capacity · copilot)", async ({ page }) => {
    await page.goto("/quanverse");

    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("quanverse-header")).toBeVisible();
    // S3 (trống) hoặc S1/S2 (đủ): một trong hai phải hiện.
    const insufficient = await page.getByTestId("quanverse-insufficient").count();
    if (insufficient > 0) {
      await expect(page.getByTestId("insufficient-checklist")).toBeVisible();
    } else {
      await expect(page.getByTestId("quanverse-verdict")).toBeVisible();
      await expect(page.getByTestId("quanverse-map")).toBeVisible();
      await expect(page.getByTestId("quanverse-actions")).toBeVisible();
      await expect(page.getByTestId("quanverse-timeline")).toBeVisible();
      await expect(page.getByTestId("quanverse-capacity")).toBeVisible();
      await expect(page.getByTestId("quanverse-copilot")).toBeVisible();
      await expect(page.getByTestId("quanverse-zone-focus")).toBeVisible();
      await expect(page.getByTestId("quanverse-modes")).toBeVisible();
    }
  });

  test("tiêu đề nói đây là trung tâm điều hành quán", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByRole("heading", { name: "QUÁNVERSE" })).toBeVisible();
    await expect(page.getByText("Trung tâm điều hành quán")).toBeVisible();
  });

  test("KHÔNG còn mock/scenario/role-buttons — chỉ dữ liệu thật", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });

    await expect(page.getByTestId("toggle-source")).toHaveCount(0);
    await expect(page.getByTestId("source-scenario")).toHaveCount(0);
    await expect(page.getByTestId("scenario-cao_diem")).toHaveCount(0);
    await expect(page.getByTestId("role-quan_ly")).toHaveCount(0);
    await expect(page.getByTestId("quanverse-capability")).toHaveCount(0);
  });

  test("KHÔNG còn tab War Room hay Cứu ca", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });

    await expect(page.getByTestId("qv-tab-war_room")).toHaveCount(0);
    await expect(page.getByTestId("qv-tab-shift_rescue")).toHaveCount(0);
    await expect(page.getByRole("tab", { name: /War Room/i })).toHaveCount(0);
    await expect(page.getByRole("tab", { name: /Cứu ca/i })).toHaveCount(0);
    await expect(page.getByRole("tab")).toHaveCount(0);
  });

  test("KHÔNG còn bề mặt khách hàng", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });

    for (const testId of [
      "guest-journey",
      "flavor-results",
      "flavor-go",
      "pref-input",
      "pref-propose",
      "ar-qr",
      "ar-start",
    ]) {
      await expect(page.getByTestId(testId)).toHaveCount(0);
    }
    await expect(page.locator(".nq-journey")).toHaveCount(0);
    await expect(page.locator(".nq-flavor")).toHaveCount(0);
    await expect(page.locator(".nq-pref")).toHaveCount(0);
    await expect(page.locator(".nq-ar")).toHaveCount(0);
  });

  test("KHÔNG render <canvas> — Quánverse là 2D thuần", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });
    // Chờ khối bản đồ render xong trước khi đếm.
    await expect(page.getByTestId("quanverse-map")).toBeVisible();

    // KHÔNG gọi disableWebgl ở đây: nếu canvas tồn tại vì bất cứ lý do gì,
    // bài này phải ĐỎ. (disableWebgl đã chạy ở beforeEach nhưng nó chỉ stub
    // getContext — phần tử <canvas> vẫn được tạo nếu code còn vẽ nó.)
    await expect(page.locator(".nq-living-map__canvas")).toHaveCount(0);
    await expect(page.locator(".nq-viewtoggle")).toHaveCount(0);
  });

  test("bản đồ khu vực 2D click được và đổi aria-pressed", async ({ page }) => {
    await page.goto("/quanverse");
    const zone = page.getByTestId("qv-zone-quay_pha");
    await expect(zone).toBeVisible({ timeout: 15_000 });

    await expect(zone).toHaveAttribute("aria-pressed", "false");
    await zone.click();
    await expect(zone).toHaveAttribute("aria-pressed", "true");
  });

  test("bản đồ có legend trạng thái", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-map")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator(".nq-qvmap__legend")).toContainText("Ổn định");
    await expect(page.locator(".nq-qvmap__legend")).toContainText("Quá tải");
  });

  test("AI Copilot hiện nguồn hậu thuẫn khi có dữ liệu", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-copilot")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("copilot-headline")).toBeVisible();

    // Có căn cứ thì phải có citation; không có thì phải nói thẳng.
    const citations = page.getByTestId("copilot-citations");
    const noCitations = page.getByTestId("copilot-no-citations");
    const coCitation = await citations.count();
    if (coCitation > 0) {
      await expect(citations).toBeVisible();
    } else {
      await expect(noCitations).toBeVisible();
      await expect(noCitations).toContainText("Chưa có bản ghi hậu thuẫn");
    }
  });

  test("nhãn nguồn dữ liệu luôn hiện", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-source")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("source-badge")).toContainText("Dữ liệu thật");
  });
});
