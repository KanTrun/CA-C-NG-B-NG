import { expect, test } from "@playwright/test";
import { disableWebgl, ensureDemoData, loginAs, resetExperienceState } from "./_helpers";

/**
 * QUÁNVERSE 2.0 Cockpit — verdict JEV · top3 rank · hỏi AI · 1 đề xuất mode.
 */

test.describe("QUÁNVERSE cockpit 2.0", () => {
  test.beforeEach(async ({ page }) => {
    await disableWebgl(page);
    await loginAs(page);
    await resetExperienceState(page);
    await ensureDemoData(page);
  });

  test("verdict JEV hiện p + căn cứ @smoke", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-verdict")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("verdict-headline")).not.toBeEmpty();
    await expect(page.getByTestId("verdict-evidence")).toContainText("Căn cứ:");
    await expect(page.getByTestId("verdict-provider")).toContainText(/JEV thật|Luật nền/);
  });

  test("top3 JEV rank hiện tối đa 3 mục @smoke", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-actions")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("actions-count")).toContainText("JEV rank");
    expect(await page.locator(".nq-qvact__item").count()).toBeLessThanOrEqual(3);
  });

  test("chọn khu vực → hiện ZoneFocus @smoke", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-zone-focus")).toBeVisible({ timeout: 15_000 });

    const zone = page.getByTestId("qv-zone-quay_pha");
    await expect(zone).toBeVisible({ timeout: 15_000 });
    await zone.click();
    await expect(zone).toHaveAttribute("aria-pressed", "true");

    await expect(page.getByTestId("quanverse-zone-focus")).toHaveAttribute(
      "data-zone",
      "quay_pha",
    );
  });

  test("hỏi AI grounded hiện câu trả lời + nguồn @smoke", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-copilot")).toBeVisible({ timeout: 15_000 });

    await page.getByTestId("copilot-ask-input").fill("Quán lúc này cần làm gì trước?");
    await page.getByTestId("copilot-ask-submit").click();

    await expect(page.getByTestId("copilot-ask-result")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("copilot-headline")).not.toBeEmpty();
  });

  test("1 đề xuất mode duy nhất: đề xuất → xác nhận", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-modes")).toBeVisible({ timeout: 15_000 });

    const propose = page.locator('[data-testid^="mode-propose-"]').first();
    const confirm = page.locator('[data-testid^="mode-confirm-"]').first();
    if ((await propose.count()) > 0) {
      await propose.click();
      await expect(confirm).toBeVisible({ timeout: 10_000 });
      await confirm.click();
    } else if ((await confirm.count()) > 0) {
      await confirm.click();
    }
    // Sau duyệt, card vẫn hiện trạng thái (Đang bật hoặc Chờ duyệt).
    await expect(page.getByTestId("quanverse-modes")).toBeVisible();
  });

  test("vẫn không có canvas / war-room tabs", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("canvas")).toHaveCount(0);
    await expect(page.getByTestId("qv-tab-war_room")).toHaveCount(0);
    await expect(page.getByTestId("quanverse-modes")).toBeVisible();
  });
});
