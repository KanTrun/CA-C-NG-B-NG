import { expect, test } from "@playwright/test";
import { loginAs } from "./_helpers";

/**
 * /hom-nay — AI FORECAST thời tiết.
 *
 * Mock API thời tiết để bài không phụ thuộc Open-Meteo mạng ngoài.
 */

const FORECAST = {
  co_du_lieu: true,
  vi_tri: { thanh_pho: "Quận 1", tinh: "Hồ Chí Minh", lat: 10.78, lon: 106.7, nguon: "gps" },
  hien_tai: { nhiet_do: 31, nhom: "mua", mo_ta: "Mưa vừa", mua_mm: 2.1, do_am: 80 },
  theo_gio: [
    { gio: 8, nhiet_do: 28, nhom: "may", mo_ta: "U ám" },
    { gio: 12, nhiet_do: 30, nhom: "mua", mo_ta: "Mưa vừa" },
    { gio: 16, nhiet_do: 29, nhom: "mua_to", mo_ta: "Mưa to" },
    { gio: 20, nhiet_do: 27, nhom: "mua", mo_ta: "Mưa nhẹ" },
  ],
  anh_huong_quan: {
    tom_tat: "Mưa vừa: khách ngoài trời thưa hơn, cân nhắc bật chế độ Trời mưa.",
    yeu_to: ["Khách ngoài trời giảm — giữ bàn trong nhà sẵn sàng."],
    de_xuat_mode: "troi_mua",
    de_xuat_mode_label: "Trời mưa",
    de_xuat_mode_href: "/quanverse",
    tone: "warn",
    he_so_ngoai_troi: 0.7,
  },
  cap_nhat_luc: "2026-09-30T02:00:00Z",
  nguon: "open-meteo",
  ngay: "2026-09-30",
};

const EMPTY = {
  co_du_lieu: false,
  can_cau_hinh: true,
  ly_do: "Chưa có vị trí quán. Lấy vị trí GPS hoặc nhập một địa chỉ.",
};

test.describe("/hom-nay AI FORECAST", () => {
  test("hiện vị trí, timeline giờ và link Quánverse", async ({ page }) => {
    await page.route("**/api/v1/thoi-tiet/hom-nay**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(FORECAST),
      }),
    );
    await loginAs(page);
    await page.goto("/hom-nay");
    const block = page.getByTestId("ai-forecast");
    await expect(block).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("ai-forecast-location")).toContainText("Quận 1");
    await expect(page.getByTestId("ai-forecast-location")).toContainText("GPS");
    await expect(page.getByTestId("ai-forecast-now")).toContainText("31");
    await expect(page.getByTestId("ai-forecast-hours")).toBeVisible();
    await expect(page.getByTestId("ai-forecast-impact")).toContainText("Ảnh hưởng quán");
    await expect(page.getByTestId("ai-forecast-mode-hint")).toContainText("Trời mưa");
    await expect(block.getByRole("link", { name: /Quánverse/i })).toHaveAttribute(
      "href",
      "/quanverse",
    );
  });

  test("empty: GPS + một ô địa chỉ, không bắt điền tỉnh/thành", async ({ page }) => {
    // Tour onboarding (`.nq-tour-mask`) chặn pointer — tắt trước khi vào trang.
    await page.addInitScript(() => {
      localStorage.setItem("nq_onboarding_v1", "1");
    });
    await page.route("**/api/v1/thoi-tiet/hom-nay**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(EMPTY),
      }),
    );
    await loginAs(page);
    await page.goto("/hom-nay");
    await expect(page.getByTestId("ai-forecast")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("ai-forecast-setup")).toBeVisible();
    await expect(page.getByTestId("ai-forecast-gps")).toBeVisible();
    await page.getByTestId("ai-forecast-show-addr").click();
    await expect(page.getByTestId("ai-forecast-dia-chi")).toBeVisible();
    await expect(page.getByTestId("ai-forecast-save-addr")).toBeVisible();
    await expect(page.locator('input[placeholder*="Tỉnh"]')).toHaveCount(0);
  });
});
