import { expect, test } from "@playwright/test";
import { disableWebgl, ensureDemoData, loginAs } from "./_helpers";

/**
 * QUÁNVERSE 2.0 mobile e2e — 390×844.
 *
 * Yêu cầu gốc: "Mobile: stack thành một cột. Verdict JEV phải nhìn thấy ngay."
 */

test.describe("QUÁNVERSE mobile", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test.beforeEach(async ({ page }) => {
    await disableWebgl(page);
    await loginAs(page);
    await ensureDemoData(page);
  });

  test("không tràn ngang", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });

    const overflow = await page.evaluate(() => ({
      scrollW: document.documentElement.scrollWidth,
      clientW: document.documentElement.clientWidth,
    }));
    expect(
      overflow.scrollW,
      `tràn ngang: ${overflow.scrollW} > ${overflow.clientW}`,
    ).toBeLessThanOrEqual(overflow.clientW + 1);
  });

  test("Verdict nhìn thấy ngay trong màn đầu", async ({ page }) => {
    await page.goto("/quanverse");
    const verdict = page.getByTestId("quanverse-verdict");
    await expect(verdict).toBeVisible({ timeout: 15_000 });

    const box = await verdict.boundingBox();
    expect(box, "không đo được khối verdict").not.toBeNull();
    // Verdict phải nằm trong màn đầu (844px).
    expect(box?.y ?? 9999).toBeLessThanOrEqual(844);
  });

  test("bố cục xếp thành một cột", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-map")).toBeVisible({ timeout: 15_000 });

    const map = await page.getByTestId("quanverse-map").boundingBox();
    const actions = await page.getByTestId("quanverse-actions").boundingBox();
    expect(map).not.toBeNull();
    expect(actions).not.toBeNull();
    // Trên mobile, cột việc cần xử lý nằm DƯỚI bản đồ (không cạnh nhau).
    expect((actions?.y ?? 0)).toBeGreaterThanOrEqual((map?.y ?? 0) + (map?.height ?? 0) - 2);
  });

  test("ô khu vực có đích chạm ≥ 44px", async ({ page }) => {
    await page.goto("/quanverse");
    const zone = page.getByTestId("qv-zone-quay_pha");
    await expect(zone).toBeVisible({ timeout: 15_000 });

    const box = await zone.boundingBox();
    expect(box).not.toBeNull();
    expect(box?.height ?? 0, "ô khu vực quá thấp để chạm").toBeGreaterThanOrEqual(44);
  });

  test("bấm khu vực trên mobile vẫn đổi được trạng thái chọn", async ({ page }) => {
    await page.goto("/quanverse");
    const zone = page.getByTestId("qv-zone-quay_thu_ngan").or(page.getByTestId("qv-zone-quay_pha"));
    await expect(zone.first()).toBeVisible({ timeout: 15_000 });
    await zone.first().click();
    await expect(zone.first()).toHaveAttribute("aria-pressed", "true");
  });
});
