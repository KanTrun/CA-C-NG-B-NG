import { expect, test } from "@playwright/test";
import { disableWebgl, loginAs, resetExperienceState } from "./_helpers";

/**
 * QUÁNVERSE Cockpit — selection bus · AI ask · modes · density.
 */

test.describe("QUÁNVERSE cockpit", () => {
  test.beforeEach(async ({ page }) => {
    await disableWebgl(page);
    await loginAs(page);
    await resetExperienceState(page);
  });

  test("chọn khu vực → hiện ZoneFocus và lọc actions", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });

    // ZoneFocus luôn chiếm chỗ (idle hoặc đã chọn) — không để lỗ trống dưới map.
    await expect(page.getByTestId("quanverse-zone-focus")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("quanverse-capability")).toBeVisible();

    // Bật mô phỏng quá tải để chắc có action gắn zone.
    const toggle = page.getByTestId("toggle-source");
    if (await toggle.count()) {
      await toggle.click();
      await page.getByTestId("scenario-qua_tai_pha").click();
    }

    const zone = page.getByTestId("qv-zone-quay_pha");
    await expect(zone).toBeVisible({ timeout: 15_000 });
    await zone.click();
    await expect(zone).toHaveAttribute("aria-pressed", "true");

    await expect(page.getByTestId("quanverse-zone-focus")).toHaveAttribute(
      "data-zone",
      "quay_pha",
    );
    await expect(page.getByTestId("actions-filter")).toBeVisible();
  });

  test("hỏi AI grounded hiện câu trả lời + nguồn", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-copilot")).toBeVisible({ timeout: 15_000 });

    const toggle = page.getByTestId("toggle-source");
    if (await toggle.count()) {
      await toggle.click();
    }

    await page.getByTestId("copilot-ask-input").fill("Khu vực nào đang quá tải?");
    await page.getByTestId("copilot-ask-submit").click();

    await expect(page.getByTestId("copilot-ask-result")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("copilot-headline")).not.toBeEmpty();
  });

  test("modes: đề xuất → xác nhận (mock)", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-modes")).toBeVisible({ timeout: 15_000 });

    const toggle = page.getByTestId("toggle-source");
    if (await toggle.count()) {
      await toggle.click();
    }

    const mode = page.getByTestId("mode-troi_mua");
    await expect(mode).toBeVisible();

    const propose = page.getByTestId("mode-propose-troi_mua");
    if (await propose.count()) {
      await propose.click();
      await expect(page.getByTestId("mode-confirm-troi_mua")).toBeVisible({
        timeout: 10_000,
      });
      await expect(page.getByTestId("mode-checklist-troi_mua")).toBeVisible();
      await page.getByTestId("mode-confirm-troi_mua").click();
      await expect(mode).toHaveAttribute("data-status", "active", { timeout: 10_000 });
      await expect(page.getByTestId("mode-checklist-troi_mua")).toContainText(
        /trong nhà|món nóng/i,
      );
    }
  });

  test("weather CTA đề xuất Trời mưa khi có de_xuat_mode", async ({ page }) => {
    await page.route("**/api/v1/thoi-tiet/hom-nay**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          co_du_lieu: true,
          vi_tri: { lat: 10.78, lon: 106.7, nguon: "gps" },
          hien_tai: { nhiet_do: 28, nhom: "mua", mo_ta: "Mưa vừa" },
          anh_huong_quan: {
            tom_tat: "Mưa: cân nhắc chế độ Trời mưa.",
            de_xuat_mode: "troi_mua",
            de_xuat_mode_label: "Trời mưa",
          },
        }),
      }),
    );
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-capacity")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("capacity-weather-hint")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("capacity-weather-propose")).toContainText(/Trời mưa/i);

    // Fixture có thể đã bật troi_mua — tắt trước để CTA đề xuất có chỗ chạy.
    const offBtn = page.getByTestId("mode-off-troi_mua");
    if (await offBtn.count()) {
      await offBtn.click();
      await expect(page.getByTestId("mode-troi_mua")).toHaveAttribute("data-status", "off", {
        timeout: 10_000,
      });
    }
    await page.getByTestId("capacity-weather-propose").click();
    await expect(page.getByTestId("mode-troi_mua")).toHaveAttribute("data-status", "draft", {
      timeout: 10_000,
    });
    await expect(page.getByTestId("mode-checklist-troi_mua")).toBeVisible();
  });

  test("capacity peak chọn được giờ", async ({ page }) => {
    await page.goto("/quanverse");
    const toggle = page.getByTestId("toggle-source");
    if (await toggle.count()) {
      await toggle.click();
      await page.getByTestId("scenario-cao_diem").click();
    }

    await expect(page.getByTestId("quanverse-capacity")).toBeVisible({ timeout: 15_000 });
    const peakBtn = page.getByTestId("capacity-peak-ask");
    if (await peakBtn.count()) {
      await peakBtn.click();
      await expect(page.getByTestId("capacity-selected")).toBeVisible();
    }
  });

  test("vẫn không có canvas / war-room tabs", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("canvas")).toHaveCount(0);
    await expect(page.getByTestId("qv-tab-war_room")).toHaveCount(0);
    await expect(page.getByTestId("quanverse-modes")).toBeVisible();
  });
});
