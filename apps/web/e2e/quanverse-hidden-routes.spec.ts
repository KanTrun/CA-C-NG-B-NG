import { expect, test } from "@playwright/test";
import { loginAs } from "./_helpers";

/**
 * QUÁNVERSE — bốn route PHỤ đã bị rút khỏi UX.
 *
 * Yêu cầu gốc: "ẩn khỏi navigation và UX … /quanverse phải độc lập về UI …
 * ưu tiên redirect về /quanverse để demo liền mạch."
 *
 * Bài này chốt bằng MÃ TRẠNG THÁI HTTP, không chỉ bằng URL cuối: `page.goto`
 * tự đi theo redirect, nên chỉ so URL sẽ không phân biệt được "redirect đúng"
 * với "trang vẫn tồn tại và tình cờ hiện nội dung giống".
 *
 * BẪY: `permanent: true` (308) bị trình duyệt cache trong cùng context. Mỗi
 * bài dùng `page.request` (context mới cho mỗi test) và `maxRedirects: 0` để
 * đọc được chính phản hồi 308 thay vì phản hồi đã đi theo.
 */

const ROUTES_DA_BO = [
  "/quanverse/war-room",
  "/quanverse/shift-rescue",
  "/quanverse/rules",
  "/quanverse/spatial-memory",
];

test.describe("QUÁNVERSE — route phụ đã rút", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
  });

  for (const duongDan of ROUTES_DA_BO) {
    test(`${duongDan} chuyển hướng về /quanverse`, async ({ page }) => {
      const res = await page.request.get(duongDan, { maxRedirects: 0 });
      expect([301, 302, 307, 308], `${duongDan} phải redirect`).toContain(res.status());
      const location = res.headers()["location"] ?? "";
      expect(location).toContain("/quanverse");
      // Không được redirect về chính nó (vòng lặp).
      expect(location.replace(/\/$/, "")).not.toBe(duongDan);
    });
  }

  test("điều hướng không còn mục nào trỏ tới route phụ", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });

    for (const nhan of ["War Room", "Cứu ca", "Quán tự viết luật", "Hồn quán"]) {
      await expect(page.getByRole("link", { name: nhan })).toHaveCount(0);
    }
  });

  test("/quanverse vẫn là điểm vào duy nhất và dùng được", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("heading", { name: "QUÁNVERSE" })).toBeVisible();
  });
});
